from django.contrib.auth import get_user_model
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from common.cargo_scoping import bound_pickup_id, filter_owned_queryset, get_request_cargo_id
from common.permissions import IsCargoManager, IsOwnerOrStaff

from .filters import ParcelFilter
from .models import Parcel, ParcelStatusHistory
from .serializers import (
    OperationHistorySerializer,
    ParcelAssignSerializer,
    ParcelScanSerializer,
    ParcelSerializer,
    ParcelStatusHistorySerializer,
    ParcelWeightSerializer,
)
from .services import ScanError, calc_delivery_price, scan_parcel

User = get_user_model()

MANAGER_ACTIONS = ("scan", "assign", "weight")


class ParcelViewSet(ReadOnlyModelViewSet):
    serializer_class = ParcelSerializer
    permission_classes = (IsAuthenticated, IsOwnerOrStaff)
    filterset_class = ParcelFilter
    queryset = Parcel.objects.none()

    def get_permissions(self):
        if self.action in MANAGER_ACTIONS:
            return [IsAuthenticated(), IsCargoManager()]
        return super().get_permissions()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Parcel.objects.none()
        queryset = Parcel.objects.select_related(
            "user", "user__pickup_point", "order", "cargo", "pickup_point"
        )
        queryset = filter_owned_queryset(queryset, self.request.user, cargo_lookup="cargo")

        # У каждого ПВЗ свой склад: привязанный оператор видит свой ПВЗ.
        # Показываем: физически принятые в этот ПВЗ (в т.ч. «ничьи», без клиента)
        # и ещё не принятые, но адресованные клиентам этого ПВЗ.
        pickup_id = bound_pickup_id(self.request.user)
        if pickup_id:
            queryset = queryset.filter(
                Q(pickup_point_id=pickup_id)
                | Q(pickup_point__isnull=True, user__pickup_point_id=pickup_id)
            )
        return queryset

    @action(detail=True, methods=("get",), url_path="history")
    def history(self, request, pk=None):
        parcel = self.get_object()
        serializer = ParcelStatusHistorySerializer(parcel.history.select_related("changed_by"), many=True)
        return Response(serializer.data)

    def _request_cargo(self, request):
        """Карго оператора. Супер обязан указать ?cargo= / cargo в теле."""
        cargo_id = get_request_cargo_id(request.user)
        if cargo_id:
            return request.user.cargo
        if request.user.is_superuser:
            override = request.data.get("cargo") or request.query_params.get("cargo")
            if override:
                from cargo.models import CargoCompany

                return CargoCompany.objects.filter(pk=override).first()
        return None

    # Статусы, доступные оператору склада в Китае (приём в Китае + отправка).
    CHINA_STATUSES = (
        Parcel.Status.WAITING_CHINA_WAREHOUSE,
        Parcel.Status.ARRIVED_CHINA_WAREHOUSE,
        Parcel.Status.SENT_TO_KYRGYZSTAN,
    )

    @extend_schema(request=ParcelScanSerializer, responses={200: ParcelSerializer})
    @action(detail=False, methods=("post",), url_path="scan")
    def scan(self, request):
        serializer = ParcelScanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Оператор Китая (не админ/не супер) может ставить только статусы Китая
        # и работает в режиме общего склада: карго берётся из заказа по треку
        # среди всех карго.
        user = request.user
        china_only = getattr(user, "is_china_staff", False) and not (
            getattr(user, "is_cargo_admin", False) or user.is_superuser
        )
        target = serializer.validated_data.get("status")
        if china_only and target and target not in self.CHINA_STATUSES:
            return Response(
                {"detail": "Оператору склада в Китае доступны только статусы Китая", "code": "forbidden_status"},
                status=403,
            )

        cargo = None if china_only else self._request_cargo(request)
        try:
            result, parcel = scan_parcel(
                serializer.validated_data["track_number"],
                cargo=cargo,
                actor=request.user,
                status=serializer.validated_data.get("status") or None,
                weight=serializer.validated_data.get("weight"),
                client_code=serializer.validated_data.get("client_code"),
                pickup_point=serializer.validated_data.get("pickup_point"),
                request=request,
                global_resolve=china_only,
            )
        except ScanError as exc:
            conflicts = {"conflict", "already_advanced", "ambiguous"}
            status_code = 409 if exc.code in conflicts else 400
            return Response({"detail": exc.message, "code": exc.code}, status=status_code)
        return Response(
            {"result": result, "parcel": ParcelSerializer(parcel).data},
            status=200 if result in ("updated", "unchanged") else 201,
        )

    @extend_schema(request=ParcelAssignSerializer, responses={200: ParcelSerializer})
    @action(detail=True, methods=("post",), url_path="assign")
    def assign(self, request, pk=None):
        parcel = self.get_object()
        if parcel.user_id is not None:
            return Response(
                {"detail": "Посылка уже привязана к клиенту"}, status=400
            )
        serializer = ParcelAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        client_code = serializer.validated_data["client_code"].strip()

        # Клиента ищем в карго посылки; для «ничьей» (cargo=None) — в карго
        # оператора, и это же карго присваиваем посылке.
        scope_cargo_id = parcel.cargo_id or get_request_cargo_id(request.user)
        candidates = User.objects.filter(client_code=client_code)
        if scope_cargo_id:
            candidates = candidates.filter(cargo_id=scope_cargo_id)
        matches = list(candidates.select_related("cargo")[:2])
        if len(matches) > 1:
            return Response(
                {"detail": "Код клиента найден в нескольких карго — уточните карго"},
                status=409,
            )
        client = matches[0] if matches else None
        if client is None:
            return Response(
                {"detail": f"Клиент с кодом {client_code} не найден"},
                status=404,
            )
        parcel.user = client
        parcel.client_code = client_code
        update_fields = ["user", "client_code", "updated_at"]
        if parcel.cargo_id is None:
            parcel.cargo = client.cargo
            update_fields.append("cargo")
        parcel._status_changed_by = request.user
        parcel.save(update_fields=update_fields)
        return Response(ParcelSerializer(parcel).data)

    @extend_schema(request=ParcelWeightSerializer, responses={200: ParcelSerializer})
    @action(detail=True, methods=("post",), url_path="weight")
    def weight(self, request, pk=None):
        """Уточнить вес посылки (приём/выдача) — цена доставки пересчитывается."""
        parcel = self.get_object()
        serializer = ParcelWeightSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        parcel.weight = serializer.validated_data["weight"]
        parcel.delivery_price = calc_delivery_price(parcel.cargo, parcel.weight)
        parcel.save(update_fields=["weight", "delivery_price", "updated_at"])
        return Response(ParcelSerializer(parcel).data)


class OperationHistoryViewSet(ReadOnlyModelViewSet):
    """История операций приём/выдача.

    Сотрудник видит только свои операции; владелец/админ карго — все по своему
    карго (с фильтром по оператору). Супер-владелец — по всем (или ?cargo=).
    Фильтры: ``type`` (receive|issue), ``operator``, ``date_from``/``date_to``,
    ``search`` (трек / код клиента / имя).
    """

    serializer_class = OperationHistorySerializer
    # Историю показываем прямо на страницах «Приём»/«Выдача»: доступ — любому
    # сотруднику карго (скоуп по роли: оператор видит только свои операции).
    permission_classes = (IsAuthenticated, IsCargoManager)
    queryset = ParcelStatusHistory.objects.none()

    RECEIVE = Parcel.Status.AT_PICKUP_POINT
    ISSUE = Parcel.Status.ISSUED
    CHINA = (Parcel.Status.ARRIVED_CHINA_WAREHOUSE, Parcel.Status.SENT_TO_KYRGYZSTAN)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ParcelStatusHistory.objects.none()
        user = self.request.user
        qs = (
            ParcelStatusHistory.objects.filter(status__in=(self.RECEIVE, self.ISSUE, *self.CHINA))
            .select_related(
                "parcel",
                "parcel__user",
                "parcel__user__pickup_point",
                "parcel__order",
                "parcel__pickup_point",
                "changed_by",
            )
            .order_by("-created_at")
        )

        is_manager = user.is_superuser or getattr(user, "is_cargo_admin", False)
        if is_manager:
            # Менеджер: скоуп по карго (+ фильтр по оператору). Супер — все/?cargo=.
            cargo_id = get_request_cargo_id(user)
            if cargo_id:
                qs = qs.filter(parcel__cargo_id=cargo_id)
            else:
                override = self.request.query_params.get("cargo")
                if override:
                    qs = qs.filter(parcel__cargo_id=override)
            operator = self.request.query_params.get("operator")
            if operator:
                qs = qs.filter(changed_by_id=operator)
        else:
            # Сотрудник (в т.ч. оператор Китая): только свои операции, любой карго —
            # в Китае посылки часто «ничьи» (cargo=None), их не отсекаем.
            qs = qs.filter(changed_by=user)

        # Тип операции.
        op_type = self.request.query_params.get("type")
        if op_type == "receive":
            qs = qs.filter(status=self.RECEIVE)
        elif op_type == "issue":
            qs = qs.filter(status=self.ISSUE)
        elif op_type == "china":
            qs = qs.filter(status__in=self.CHINA)

        # Диапазон дат (по дате операции).
        d_from = self.request.query_params.get("date_from")
        d_to = self.request.query_params.get("date_to")
        if d_from:
            qs = qs.filter(created_at__date__gte=d_from)
        if d_to:
            qs = qs.filter(created_at__date__lte=d_to)

        # Поиск.
        search = (self.request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(parcel__track_number__icontains=search)
                | Q(parcel__client_code__icontains=search)
                | Q(parcel__user__full_name__icontains=search)
            )
        # Пагинации в проекте нет — ограничиваем последними 500 операциями.
        return qs[:500]
