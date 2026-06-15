from rest_framework import serializers

from parcels.models import Parcel

from .models import CityDeliveryRequest, CityDeliveryTariff


class CityDeliveryTariffSerializer(serializers.ModelSerializer):
    pickup_point_title = serializers.CharField(
        source="pickup_point.title", read_only=True
    )

    class Meta:
        model = CityDeliveryTariff
        fields = (
            "id",
            "title",
            "base_price",
            "price_per_kg",
            "free_weight_kg",
            "min_price",
            "is_default",
            "is_active",
            "cargo",
            "pickup_point",
            "pickup_point_title",
        )


class ManagedCityDeliveryTariffSerializer(serializers.ModelSerializer):
    """CRUD тарифов для владельца карго. ``cargo`` проставляется во view."""

    class Meta:
        model = CityDeliveryTariff
        fields = (
            "id",
            "title",
            "base_price",
            "price_per_kg",
            "free_weight_kg",
            "min_price",
            "is_default",
            "is_active",
            "cargo",
            "pickup_point",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "cargo", "created_at", "updated_at")

    def validate_pickup_point(self, pickup_point):
        request = self.context.get("request")
        if (
            pickup_point is not None
            and request is not None
            and not request.user.is_superuser
            and pickup_point.cargo_id != request.user.cargo_id
        ):
            raise serializers.ValidationError("ПВЗ принадлежит другому карго-центру")
        return pickup_point


class CityDeliveryRequestSerializer(serializers.ModelSerializer):
    status_display_name = serializers.CharField(source="get_status_display", read_only=True)
    tariff_title = serializers.CharField(source="tariff.title", read_only=True)
    track_number = serializers.CharField(source="parcel.track_number", read_only=True)

    class Meta:
        model = CityDeliveryRequest
        fields = (
            "id",
            "user",
            "parcel",
            "track_number",
            "tariff",
            "tariff_title",
            "address",
            "recipient_name",
            "recipient_phone",
            "comment",
            "price",
            "status",
            "status_display_name",
            "delivery_date",
            "delivery_time_slot",
            "delivered_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "user",
            "tariff",
            "tariff_title",
            "price",
            "status",
            "status_display_name",
            "delivered_at",
            "created_at",
            "updated_at",
        )

    def validate_parcel(self, parcel):
        request = self.context["request"]
        if not request.user.is_staff and parcel.user_id != request.user.id:
            raise serializers.ValidationError(
                "Можно создать заявку только для собственной посылки"
            )
        if parcel.status in {
            Parcel.Status.ISSUED,
            Parcel.Status.DELIVERED,
            Parcel.Status.CANCELLED,
        }:
            raise serializers.ValidationError(
                "Невозможно заказать доставку для уже завершённой или отменённой посылки"
            )
        return parcel

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and not request.user.is_anonymous and not request.user.is_staff:
            self.fields["parcel"].queryset = Parcel.objects.filter(user=request.user)


class CityDeliveryEstimateRequestSerializer(serializers.Serializer):
    parcel = serializers.IntegerField(help_text="ID посылки")


class CityDeliveryEstimateResponseSerializer(serializers.Serializer):
    parcel = serializers.IntegerField()
    weight = serializers.DecimalField(max_digits=10, decimal_places=3, allow_null=True)
    price = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    tariff = CityDeliveryTariffSerializer(allow_null=True)
