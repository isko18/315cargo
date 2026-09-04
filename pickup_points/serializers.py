from rest_framework import serializers

from .models import PickupPoint


class PickupPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = PickupPoint
        fields = ("id", "title", "address", "phone", "work_schedule")


class ManagedPickupPointSerializer(serializers.ModelSerializer):
    """CRUD ПВЗ для владельца карго. ``cargo`` проставляется во view."""

    client_code_next = serializers.CharField(source="next_client_code", read_only=True)

    class Meta:
        model = PickupPoint
        fields = (
            "id",
            "cargo",
            "title",
            "address",
            "phone",
            "work_schedule",
            "client_code_prefix",
            "client_code_seq",
            "client_code_next",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "cargo",
            "client_code_seq",
            "created_at",
            "updated_at",
        )

    def validate_client_code_prefix(self, value):
        from cargo.serializers import normalize_pickup_code_prefix

        return normalize_pickup_code_prefix(value, instance=self.instance)
