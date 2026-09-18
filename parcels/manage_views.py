"""Управление посылками из панели (веб и мобильная).

Отдельный модуль, чтобы не смешивать с клиентским ParcelViewSet: у него другой
скоуп (клиент видит только свои посылки) и другой набор операций.

До этого правка посылки собиралась из трёх вызовов — assign/, weight/ и scan/.
Смена статуса через scan/ работает, но пишет лишнюю строку в историю приёмки:
операция выглядит так, будто коробку снова сканировали на складе.
"""

from django.db import transaction
from django.db.models import Q
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from common.cargo_scoping import bound_pickup_id, get_request_cargo_id
from common.permissions import IsCargoManager
from pickup_points.models import PickupPoint

from .models import Parcel
from .serializers import ParcelSerializer
from .services import ScanError, calc_delivery_price, scan_parcel, update_parcel_status

# Оператору склада в Китае доступны только «китайские» статусы — та же логика,
# что уже стоит на scan/.
CHINA_STATUSES = (
    Parcel.Status.WAITING_CHINA_WAREHOUSE,
    Parcel.Status.ARRIVED_CHINA_WAREHOUSE,
    Parcel.Status.SENT_TO_KYRGYZSTAN,
)


class ParcelUpdateSerializer(serializers.Serializer):
    """Поля, которые панель правит в карточке товара."""

    status = serializers.ChoiceField(choices=Parcel.Status.choices, required=False)
    weight = serializers.DecimalField(
        max_digits=10, decimal_places=3, required=False, allow_null=True
    )
    client_code = serializers.CharField(required=False, allow_blank=True)
    pickup_point = serializers.PrimaryKeyRelatedField(
        queryset=PickupPoint.objects.all(), required=False, allow_null=True
    )
    location = serializers.CharField(required=False, allow_blank=True)


class BulkScanItemSerializer(serializers.Serializer):
    # allow_blank, чтобы пустой трек попал в построчные ошибки: иначе одна
    # пустая строка отвергала бы всю накладную на валидации.
    track_number = serializers.CharField(allow_blank=True)
    weight = serializers.DecimalField(
        max_digits=10, decimal_places=3, required=False, allow_null=True
    )
    client_code = serializers.CharField(required=False, allow_blank=True)


class BulkScanSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Parcel.Status.choices)
    pickup_point = serializers.PrimaryKeyRelatedField(
        queryset=PickupPoint.objects.all(), required=False, allow_null=True
    )
    items = BulkScanItemSerializer(many=True)


class BulkStatusSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField())
    status = serializers.ChoiceField(choices=Parcel.Status.choices)


@extend_schema_view(
    partial_update=extend_schema(
        tags=["manage"], request=ParcelUpdateSerializer, responses=ParcelSerializer
    ),
    bulk_scan=extend_schema(tags=["manage"], request=BulkScanSerializer, responses={200: dict}),
    bulk_status=extend_schema(tags=["manage"], request=BulkStatusSerializer, responses={200: dict}),
)
class ManagedParcelViewSet(GenericViewSet):
    """Правка посылок сотрудником: одиночная и пачкой."""

    permission_classes = (IsAuthenticated, IsCargoManager)
    serializer_class = ParcelUpdateSerializer
    queryset = Parcel.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Parcel.objects.none()
        qs = Parcel.objects.select_related("user", "pickup_point", "cargo", "order")
        cargo_id = get_request_cargo_id(self.request.user)
        if cargo_id:
            qs = qs.filter(cargo_id=cargo_id)
        pickup_id = bound_pickup_id(self.request.user)
        if pickup_id:
            # Привязанный оператор правит только то, что лежит в его ПВЗ, либо
            # адресовано его клиентам (ещё не принято) — тот же охват, что и
            # в фильтре списка посылок.
            qs = qs.filter(
                Q(pickup_point_id=pickup_id)
                | Q(pickup_point__isnull=True, user__pickup_point_id=pickup_id)
            )
        return qs

    def _china_only(self):
        user = self.request.user
        return getattr(user, "is_china_staff", False) and not (
            getattr(user, "is_cargo_admin", False) or user.is_superuser
        )

    def _forbidden_status(self, status):
        if status and self._china_only() and status not in CHINA_STATUSES:
            return "Оператору склада в Китае доступны только статусы Китая"
        return None

    def partial_update(self, request, pk=None):
        parcel = self.get_queryset().filter(pk=pk).first()
        if parcel is None:
            return Response({"detail": "Посылка не найдена"}, status=404)

        serializer = ParcelUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        forbidden = self._forbidden_status(data.get("status"))
        if forbidden:
            return Response({"detail": forbidden, "code": "forbidden_status"}, status=403)

        has_point = "pickup_point" in data
        point = data.get("pickup_point")
        if has_point and point is not None and point.cargo_id != parcel.cargo_id:
            # ПВЗ чужого карго сделал бы посылку невидимой для обеих сторон.
            return Response({"detail": "Пункт выдачи принадлежит другому карго"}, status=400)

        with transaction.atomic():
            fields = []
            if "client_code" in data:
                code = (data["client_code"] or "").strip()
                if code:
                    from users.models import User

                    client = User.objects.filter(
                        client_code__iexact=code, cargo_id=parcel.cargo_id
                    ).first()
                    if client is None:
                        return Response(
                            {"detail": "Клиент с кодом %s не найден" % code}, status=400
                        )
                    parcel.user = client
                    parcel.client_code = client.client_code
                    fields += ["user", "client_code"]

            if "weight" in data:
                parcel.weight = data["weight"]
                parcel.delivery_price = calc_delivery_price(parcel.cargo, data["weight"])
                fields += ["weight", "delivery_price"]

            if has_point:
                parcel.pickup_point = point
                fields.append("pickup_point")
                if point is not None:
                    parcel.location = point.address
                    fields.append("location")

            if "location" in data:
                parcel.location = data["location"]
                fields.append("location")

            if fields:
                parcel.save(update_fields=[*dict.fromkeys(fields), "updated_at"])

            # Статус меняем сервисом: он пишет историю и шлёт уведомление.
            if data.get("status") and data["status"] != parcel.status:
                update_parcel_status(parcel, data["status"], changed_by=request.user)

        parcel.refresh_from_db()
        return Response(ParcelSerializer(parcel).data)

    @action(detail=False, methods=("post",), url_path="bulk-scan")
    def bulk_scan(self, request):
        """Приём накладной пачкой.

        Семантика строки — как у scan/ (upsert по треку). Каждая строка в своей
        транзакции: одна плохая не должна отменять всю накладную.
        """
        serializer = BulkScanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        forbidden = self._forbidden_status(data["status"])
        if forbidden:
            return Response({"detail": forbidden, "code": "forbidden_status"}, status=403)

        china_only = self._china_only()
        cargo = None
        if not china_only:
            from cargo.models import CargoCompany

            cargo_id = get_request_cargo_id(request.user)
            cargo = CargoCompany.objects.filter(pk=cargo_id).first() if cargo_id else None
        point = data.get("pickup_point")

        created = 0
        updated = 0
        errors = []
        for index, item in enumerate(data["items"]):
            track = (item.get("track_number") or "").strip()
            if not track:
                errors.append({"index": index, "track_number": "", "error": "Пустой трек-номер"})
                continue
            try:
                with transaction.atomic():
                    result, _parcel = scan_parcel(
                        track,
                        cargo=cargo,
                        actor=request.user,
                        status=data["status"],
                        weight=item.get("weight"),
                        client_code=(item.get("client_code") or "").strip() or None,
                        pickup_point=point.id if point else None,
                        request=request,
                        global_resolve=china_only,
                    )
            except ScanError as exc:
                errors.append({"index": index, "track_number": track, "error": exc.message})
                continue
            except Exception as exc:  # неожиданная ошибка не должна рвать накладную
                errors.append({"index": index, "track_number": track, "error": str(exc)})
                continue
            if result in ("updated", "unchanged"):
                updated += 1
            else:
                created += 1

        return Response({"created": created, "updated": updated, "errors": errors})

    @action(detail=False, methods=("post",), url_path="bulk-status")
    def bulk_status(self, request):
        """Смена статуса посылкам, выделенным галочками в списке."""
        serializer = BulkStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        forbidden = self._forbidden_status(data["status"])
        if forbidden:
            return Response({"detail": forbidden, "code": "forbidden_status"}, status=403)

        found = {p.id: p for p in self.get_queryset().filter(pk__in=data["ids"])}

        updated = 0
        errors = []
        for index, pid in enumerate(data["ids"]):
            parcel = found.get(pid)
            if parcel is None:
                # Чужое карго и чужой ПВЗ выглядят одинаково: не найдено.
                errors.append({"index": index, "id": pid, "error": "Посылка не найдена"})
                continue
            if parcel.status == data["status"]:
                continue
            try:
                with transaction.atomic():
                    update_parcel_status(parcel, data["status"], changed_by=request.user)
                updated += 1
            except Exception as exc:
                errors.append({"index": index, "id": pid, "error": str(exc)})

        return Response({"updated": updated, "errors": errors})
