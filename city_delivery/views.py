from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from common.cargo_scoping import (
    bound_pickup_id,
    filter_owned_queryset,
    get_request_cargo_id,
)
from common.permissions import HasTabAccess, IsCargoManager, IsOwnerOrStaff
from parcels.models import Parcel

from .models import CityDeliveryRequest, CityDeliveryTariff
from .serializers import (
    CityDeliveryEstimateRequestSerializer,
    CityDeliveryEstimateResponseSerializer,
    CityDeliveryRequestSerializer,
    CityDeliveryTariffSerializer,
    ManagedCityDeliveryRequestSerializer,
    ManagedCityDeliveryTariffSerializer,
)
from .services import calculate_price


class CityDeliveryRequestViewSet(ModelViewSet):
    serializer_class = CityDeliveryRequestSerializer
    permission_classes = (IsAuthenticated, IsOwnerOrStaff)
    http_method_names = ("get", "post", "head", "options")
    queryset = CityDeliveryRequest.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CityDeliveryRequest.objects.none()
        queryset = CityDeliveryRequest.objects.select_related(
            "user", "parcel", "tariff", "courier"
        )
        return filter_owned_queryset(queryset, self.request.user)

    def perform_create(self, serializer):
        parcel = serializer.validated_data["parcel"]
        price, tariff = calculate_price(parcel)
        status = (
            CityDeliveryRequest.Status.PRICE_CALCULATED
            if price is not None
            else CityDeliveryRequest.Status.CREATED
        )
        serializer.save(
            user=self.request.user,
            tariff=tariff,
            price=price,
            status=status,
        )

    @extend_schema(
        request=CityDeliveryEstimateRequestSerializer,
        responses={200: CityDeliveryEstimateResponseSerializer},
    )
    @action(detail=False, methods=("post",), url_path="estimate")
    def estimate(self, request):
        parcel_id = request.data.get("parcel")
        if not parcel_id:
            return Response({"detail": "parcel is required"}, status=400)
        queryset = Parcel.objects.all()
        queryset = filter_owned_queryset(queryset, request.user)
        parcel = queryset.filter(pk=parcel_id).first()
        if not parcel:
            return Response({"detail": "parcel not found"}, status=404)
        price, tariff = calculate_price(parcel)
        return Response(
            {
                "parcel": parcel.id,
                "weight": parcel.weight,
                "price": price,
                "tariff": (
                    CityDeliveryTariffSerializer(tariff).data if tariff else None
                ),
            }
        )


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


class ManagedCityDeliveryRequestViewSet(ModelViewSet):
    """Панель: заявки на доставку по городу — просмотр и смена статуса."""

    serializer_class = ManagedCityDeliveryRequestSerializer
    permission_classes = (IsAuthenticated, IsCargoManager, HasTabAccess)
    required_tab = "delivery"
    http_method_names = ("get", "patch", "head", "options")
    queryset = CityDeliveryRequest.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return CityDeliveryRequest.objects.none()
        qs = CityDeliveryRequest.objects.select_related("user", "user__pickup_point", "parcel", "tariff")
        cargo_id = get_request_cargo_id(self.request.user)
        if cargo_id:
            qs = qs.filter(user__cargo_id=cargo_id)
        pickup_id = bound_pickup_id(self.request.user)
        if pickup_id:
            qs = qs.filter(user__pickup_point_id=pickup_id)
        return qs.order_by("-created_at")

    def perform_update(self, serializer):
        from parcels.services import update_parcel_status

        old_status = serializer.instance.status
        instance = serializer.save()
        # Бизнес-логика: отметки времени и синхронизация статуса посылки.
        if instance.status != old_status:
            if instance.status == CityDeliveryRequest.Status.DELIVERED:
                if instance.delivered_at is None:
                    instance.delivered_at = timezone.now()
                    instance.save(update_fields=["delivered_at"])
                update_parcel_status(instance.parcel, Parcel.Status.DELIVERED, comment="Доставлено по городу")
            elif instance.status == CityDeliveryRequest.Status.IN_DELIVERY:
                update_parcel_status(instance.parcel, Parcel.Status.CITY_DELIVERY, comment="Передан на доставку")


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
