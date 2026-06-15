from rest_framework import serializers

from .models import PickupPoint


class PickupPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = PickupPoint
        fields = ("id", "title", "address", "phone", "work_schedule")


class ManagedPickupPointSerializer(serializers.ModelSerializer):
    """CRUD ПВЗ для владельца карго. ``cargo`` проставляется во view."""

    class Meta:
        model = PickupPoint
        fields = (
            "id",
            "cargo",
            "title",
            "address",
            "phone",
            "work_schedule",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "cargo", "created_at", "updated_at")
