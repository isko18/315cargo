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
