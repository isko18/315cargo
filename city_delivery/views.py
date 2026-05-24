from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from common.cargo_scoping import filter_owned_queryset, filter_queryset_by_cargo
from common.permissions import IsOwnerOrStaff
from parcels.models import Parcel

from .models import CityDeliveryRequest, CityDeliveryTariff
from .serializers import (
    CityDeliveryEstimateRequestSerializer,
    CityDeliveryEstimateResponseSerializer,
    CityDeliveryRequestSerializer,
    CityDeliveryTariffSerializer,
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
            "pickup_point", "pickup_point__cargo"
        )
        return filter_queryset_by_cargo(
            queryset, self.request.user, lookup="pickup_point__cargo"
        )
