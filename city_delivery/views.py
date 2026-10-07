from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import status as http
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from common.cargo_scoping import (
    bound_pickup_id,
    switcher_pickup_id,
    filter_owned_queryset,
    get_request_cargo_id,
)
from common.permissions import HasTabAccess, IsCargoManager, IsOwnerOrStaff
from parcels.models import Parcel

from .models import CityDeliveryPoint, CityDeliveryRequest, CityDeliveryTariff
from .serializers import (
    AdoptSuggestionsRequestSerializer,
    AdoptSuggestionsResponseSerializer,
    CityDeliveryConflictSerializer,
    CityDeliveryEstimateRequestSerializer,
    CityDeliveryEstimateResponseSerializer,
    CityDeliveryPointSerializer,
    CityDeliveryRequestSerializer,
    CityDeliveryRequestWriteSerializer,
    CityDeliverySuggestionSerializer,
    CityDeliveryTariffSerializer,
    ManagedCityDeliveryPointSerializer,
    ManagedCityDeliveryRequestSerializer,
    ManagedCityDeliveryTariffSerializer,
)
from .services import (
    CLOSED_STATUSES,
    DeliveryInProgress,
    adopt_suggestions,
    cancel_client_request,
    group_suggestions,
    live_request_for,
    on_status_changed,
    open_suggestions,
    price_for,
    save_client_request,
)

Status = CityDeliveryRequest.Status

_CONFLICT = OpenApiResponse(
    CityDeliveryConflictSerializer,
    description="Курьер уже взял заявку: менять поздно. В id — эта заявка.",
)


def _conflict(request):
    return Response(
        {
            "detail": "Заявка уже у курьера — изменить или отменить её нельзя",
            "id": request.pk,
        },
        status=http.HTTP_409_CONFLICT,
    )


def _with_point_stats(queryset):
    live = ~Q(requests__status__in=CLOSED_STATUSES)
    return queryset.annotate(
        clients_count=Count(
            "requests__user",
            distinct=True,
            filter=~Q(requests__status=Status.CANCELLED),
        ),
        active_requests=Count("requests", distinct=True, filter=live),
        delivered_count=Count(
            "requests", distinct=True, filter=Q(requests__status=Status.DELIVERED)
        ),
    )


@extend_schema_view(
    list=extend_schema(summary="Мои заявки на доставку по городу"),
    retrieve=extend_schema(summary="Заявка на доставку по городу"),
)
class CityDeliveryRequestViewSet(ModelViewSet):
    """Доставка по городу для клиента: одна живая заявка на клиента."""

    serializer_class = CityDeliveryRequestSerializer
    permission_classes = (IsAuthenticated, IsOwnerOrStaff)
    http_method_names = ("get", "post", "patch", "head", "options")
    queryset = CityDeliveryRequest.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CityDeliveryRequest.objects.none()
        queryset = CityDeliveryRequest.objects.select_related(
            "user", "parcel", "tariff", "courier", "delivery_point"
        ).prefetch_related("parcels")
        if self.action in ("partial_update", "cancel"):
            # Менять заявку может только сам клиент: посылки и точки в анкете
            # проверяются по нему.
            return queryset.filter(user=self.request.user)
        return filter_owned_queryset(queryset, self.request.user)

    def _respond(self, instance, status_code=http.HTTP_200_OK):
        # Заново из базы: состав менялся через M2M, а prefetch на объекте старый.
        instance = (
            CityDeliveryRequest.objects.select_related("parcel", "tariff", "delivery_point")
            .prefetch_related("parcels")
            .get(pk=instance.pk)
        )
        return Response(self.get_serializer(instance).data, status=status_code)

    @extend_schema(
        summary="Оформить доставку (или обновить живую заявку)",
        description=(
            "У клиента одна живая заявка. Нет её — создаётся (201). Есть и курьер "
            "её ещё не взял — обновляется этой анкетой целиком (200, тот же id). "
            "Курьер уже взял — 409 с id заявки.\n\n"
            "Без `parcels` заявка постоянная (`is_standing`): забирает посылки, "
            "что уже лежат в ПВЗ, и подхватывает приходящие; после доставки "
            "открывается заново с той же точкой.\n\n"
            "Куда — `delivery_point` или `suggested_point`; `address` и `parcel` "
            "оставлены для старых версий."
        ),
        request=CityDeliveryRequestWriteSerializer,
        responses={
            201: CityDeliveryRequestSerializer,
            200: CityDeliveryRequestSerializer,
            409: _CONFLICT,
        },
    )
    def create(self, request, *args, **kwargs):
        user = request.user
        with transaction.atomic():
            # Два быстрых нажатия «Оформить» не должны родить две заявки.
            get_user_model().objects.select_for_update().filter(pk=user.pk).first()
            live = live_request_for(user)
            write = CityDeliveryRequestWriteSerializer(
                live, data=request.data, context=self.get_serializer_context()
            )
            write.is_valid(raise_exception=True)
            try:
                instance, created = save_client_request(user, write.validated_data, live)
            except DeliveryInProgress as exc:
                return _conflict(exc.request)
        return self._respond(instance, http.HTTP_201_CREATED if created else http.HTTP_200_OK)

    @extend_schema(
        summary="Изменить заявку",
        description="Точку, получателя, состав — пока курьер не взял заявку.",
        request=CityDeliveryRequestWriteSerializer,
        responses={200: CityDeliveryRequestSerializer, 409: _CONFLICT},
    )
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        write = CityDeliveryRequestWriteSerializer(
            instance, data=request.data, partial=True, context=self.get_serializer_context()
        )
        write.is_valid(raise_exception=True)
        try:
            instance, _ = save_client_request(
                request.user, write.validated_data, instance, partial=True
            )
        except DeliveryInProgress as exc:
            return _conflict(exc.request)
        return self._respond(instance)

    @extend_schema(
        summary="Отменить заявку",
        request=None,
        responses={200: CityDeliveryRequestSerializer, 409: _CONFLICT},
    )
    @action(detail=True, methods=("post",))
    def cancel(self, request, pk=None):
        instance = self.get_object()
        try:
            cancel_client_request(instance)
        except DeliveryInProgress as exc:
            return _conflict(exc.request)
        return self._respond(instance)

    @extend_schema(
        summary="Сколько будет стоить",
        description=(
            "Без тарифа у карго — 0: доставка бесплатная. Посылки необязательны."
        ),
        request=CityDeliveryEstimateRequestSerializer,
        responses={200: CityDeliveryEstimateResponseSerializer},
    )
    @action(detail=False, methods=("post",), url_path="estimate")
    def estimate(self, request):
        body = CityDeliveryEstimateRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        ids = list(body.validated_data.get("parcels") or [])
        if body.validated_data.get("parcel"):
            ids.append(body.validated_data["parcel"])
        parcels = list(
            filter_owned_queryset(Parcel.objects.all(), request.user)
            .filter(pk__in=ids)
            .select_related("user")
        )
        if ids and not parcels:
            return Response({"detail": "parcel not found"}, status=404)
        owner = parcels[0].user if parcels else request.user
        price, tariff = price_for(owner, parcels)
        return Response(
            {
                "parcel": parcels[0].id if parcels else None,
                "parcels": [p.id for p in parcels],
                "weight": sum((p.weight or 0) for p in parcels) if parcels else None,
                "price": price,
                "tariff": CityDeliveryTariffSerializer(tariff).data if tariff else None,
            }
        )


@extend_schema_view(
    list=extend_schema(summary="Точки доставки по городу"),
    retrieve=extend_schema(summary="Точка доставки по городу"),
)
class CityDeliveryPointViewSet(ReadOnlyModelViewSet):
    """Справочник точек для клиента: только активные точки своего карго."""

    serializer_class = CityDeliveryPointSerializer
    permission_classes = (IsAuthenticated,)
    pagination_class = None
    queryset = CityDeliveryPoint.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CityDeliveryPoint.objects.none()
        cargo_id = self.request.user.cargo_id
        if not cargo_id:
            return CityDeliveryPoint.objects.none()
        return _with_point_stats(
            CityDeliveryPoint.objects.filter(cargo_id=cargo_id, is_active=True)
        ).order_by("position", "title")


class CityDeliveryTariffViewSet(ReadOnlyModelViewSet):
    serializer_class = CityDeliveryTariffSerializer
    permission_classes = (IsAuthenticated,)

    def get_queryset(self):
        queryset = CityDeliveryTariff.objects.filter(is_active=True).select_related(
            "pickup_point", "pickup_point__cargo", "cargo"
        )
        cargo_id = get_request_cargo_id(self.request.user)
        if cargo_id:
            # Tariffs scoped to the cargo (via pickup point or directly), plus
            # truly global tariffs (no cargo and no pickup point).
            return queryset.filter(
                Q(pickup_point__cargo_id=cargo_id)
                | Q(cargo_id=cargo_id)
                | Q(cargo__isnull=True, pickup_point__isnull=True)
            )
        return queryset


_BOOL = OpenApiTypes.BOOL


@extend_schema_view(
    list=extend_schema(
        summary="Заявки на доставку по городу",
        parameters=[
            OpenApiParameter("status", str, description="Статус заявки"),
            OpenApiParameter("delivery_point", int, description="ID точки"),
            OpenApiParameter(
                "suggested", _BOOL,
                description="true — только с предложенной клиентом точкой, ещё не "
                "переведённой в справочник",
            ),
            OpenApiParameter(
                "has_parcels", _BOOL,
                description="true — скрыть пустые постоянные заявки (курьеру нечего везти)",
            ),
            OpenApiParameter("pickup_point", int, description="Переключатель ПВЗ"),
        ],
    ),
)
class ManagedCityDeliveryRequestViewSet(ModelViewSet):
    """Панель: заявки на доставку по городу — просмотр, смена статуса и точки."""

    serializer_class = ManagedCityDeliveryRequestSerializer
    permission_classes = (IsAuthenticated, IsCargoManager, HasTabAccess)
    required_tab = "delivery"
    http_method_names = ("get", "patch", "head", "options")
    queryset = CityDeliveryRequest.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CityDeliveryRequest.objects.none()
        qs = CityDeliveryRequest.objects.select_related(
            "user", "user__pickup_point", "parcel", "tariff", "delivery_point"
        ).prefetch_related("parcels")
        cargo_id = get_request_cargo_id(self.request.user)
        if cargo_id:
            qs = qs.filter(user__cargo_id=cargo_id)
        pickup_id = bound_pickup_id(self.request.user)
        if pickup_id:
            qs = qs.filter(user__pickup_point_id=pickup_id)
        params = self.request.query_params
        # Переключатель ПВЗ в шапке панели: заявка принадлежит пункту клиента.
        switched = switcher_pickup_id(self.request.user, params.get("pickup_point"))
        if switched:
            qs = qs.filter(user__pickup_point_id=switched)
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("delivery_point"):
            qs = qs.filter(delivery_point_id=params["delivery_point"])
        if params.get("suggested") == "true":
            qs = qs.filter(delivery_point__isnull=True).exclude(suggested_point="")
        if params.get("has_parcels") == "true":
            through = CityDeliveryRequest.parcels.through
            qs = qs.filter(
                Exists(through.objects.filter(citydeliveryrequest_id=OuterRef("pk")))
            )
        return qs.order_by("-created_at")

    def perform_update(self, serializer):
        old_status = serializer.instance.status
        instance = serializer.save()
        on_status_changed(instance, old_status)


class ManagedCityDeliveryPointViewSet(ModelViewSet):
    """Панель: справочник точек доставки своего карго и предложения клиентов."""

    serializer_class = ManagedCityDeliveryPointSerializer
    permission_classes = (IsAuthenticated, IsCargoManager, HasTabAccess)
    # Как у manage/pickup-points/: точки — тоже справочник мест карго.
    required_tab = "pickup"
    queryset = CityDeliveryPoint.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CityDeliveryPoint.objects.none()
        qs = CityDeliveryPoint.objects.all()
        cargo_id = get_request_cargo_id(self.request.user)
        if cargo_id:
            qs = qs.filter(cargo_id=cargo_id)
        return _with_point_stats(qs).order_by("position", "title")

    def perform_create(self, serializer):
        cargo = self.request.user.cargo
        if cargo is None:
            raise ValidationError("Точки заводит владелец карго-центра")
        serializer.save(cargo=cargo)

    @extend_schema(
        summary="Удалить точку",
        description=(
            "Точку без заявок удаляем (204). С заявками — выключаем (200): "
            "клиенту она больше не видна, а история заявок не ломается."
        ),
        responses={
            200: ManagedCityDeliveryPointSerializer,
            204: OpenApiResponse(description="Удалена"),
        },
    )
    def destroy(self, request, *args, **kwargs):
        point = self.get_object()
        if point.requests.exists():
            point.is_active = False
            point.save(update_fields=["is_active", "updated_at"])
            return Response(self.get_serializer(self.get_object()).data)
        point.delete()
        return Response(status=http.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="Предложенные клиентами точки",
        description=(
            "Живые заявки со своей точкой, сгруппированные по месту без учёта "
            "регистра и пробелов. Сверху — куда просит больше всего клиентов."
        ),
        responses={200: CityDeliverySuggestionSerializer(many=True)},
    )
    @action(detail=False, methods=("get",), pagination_class=None)
    def suggestions(self, request):
        qs = open_suggestions(
            get_request_cargo_id(request.user), bound_pickup_id(request.user)
        )
        rows = group_suggestions(qs)
        return Response(CityDeliverySuggestionSerializer(rows, many=True).data)

    @extend_schema(
        summary="Перевести предложения в эту точку",
        description=(
            "Все живые заявки с таким же предложением получают эту точку, "
            "предложение у них снимается."
        ),
        request=AdoptSuggestionsRequestSerializer,
        responses={200: AdoptSuggestionsResponseSerializer},
    )
    @action(detail=True, methods=("post",), url_path="adopt-suggestions")
    def adopt_suggestions(self, request, pk=None):
        point = self.get_object()
        body = AdoptSuggestionsRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        updated = adopt_suggestions(point, body.validated_data["text"], point.cargo_id)
        return Response({"updated": updated})


class ManagedCityDeliveryTariffViewSet(ModelViewSet):
    """Панель владельца карго: CRUD тарифов своего карго."""

    serializer_class = ManagedCityDeliveryTariffSerializer
    permission_classes = (IsAuthenticated, IsCargoManager, HasTabAccess)
    required_tab = "delivery_tariff"
    queryset = CityDeliveryTariff.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CityDeliveryTariff.objects.none()
        queryset = CityDeliveryTariff.objects.select_related("pickup_point", "cargo")
        cargo_id = get_request_cargo_id(self.request.user)
        if cargo_id:
            return queryset.filter(cargo_id=cargo_id)
        return queryset

    def perform_create(self, serializer):
        cargo = self.request.user.cargo
        if cargo is None:
            raise ValidationError(
                "Создание тарифа доступно только владельцу карго-центра"
            )
        serializer.save(cargo=cargo)
