from rest_framework import serializers

from pickup_points.models import PickupPoint

from .models import CargoCompany


class PickupPointBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = PickupPoint
        fields = ("id", "title", "address", "phone", "work_schedule")


class CargoCompanySerializer(serializers.ModelSerializer):
    pickup_points = serializers.SerializerMethodField()

    class Meta:
        model = CargoCompany
        fields = (
            "id",
            "title",
            "slug",
            "description",
            "logo",
            "phone",
            "address",
            "pickup_points",
        )

    def get_pickup_points(self, obj):
        points = obj.pickup_points.filter(is_active=True)
        return PickupPointBriefSerializer(points, many=True).data


class MyCargoSerializer(serializers.ModelSerializer):
    """Профиль карго для редактирования владельцем (slug/is_active read-only)."""

    class Meta:
        model = CargoCompany
        fields = (
            "id",
            "title",
            "slug",
            "description",
            "logo",
            "phone",
            "address",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "slug", "is_active", "created_at", "updated_at")


class CargoOverviewItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    slug = serializers.CharField()
    is_active = serializers.BooleanField()
    users_count = serializers.IntegerField()
    parcels_count = serializers.IntegerField()
    orders_count = serializers.IntegerField()
    pickup_points_count = serializers.IntegerField()


class AdminOverviewSerializer(serializers.Serializer):
    totals = serializers.DictField()
    per_cargo = CargoOverviewItemSerializer(many=True)
