from rest_framework import serializers

from .models import Parcel, ParcelStatusHistory


class ParcelSerializer(serializers.ModelSerializer):
    status_display_name = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Parcel
        fields = (
            "id",
            "cargo",
            "user",
            "order",
            "track_number",
            "client_code",
            "status",
            "status_display_name",
            "location",
            "weight",
            "volume",
            "delivery_price",
            "arrived_at",
            "issued_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "cargo",
            "user",
            "client_code",
            "created_at",
            "updated_at",
        )


class ParcelScanSerializer(serializers.Serializer):
    track_number = serializers.CharField(max_length=128)
    status = serializers.ChoiceField(
        choices=Parcel.Status.choices, required=False, allow_blank=True
    )


class ParcelAssignSerializer(serializers.Serializer):
    client_code = serializers.CharField(max_length=16)


class ParcelStatusHistorySerializer(serializers.ModelSerializer):
    status_display_name = serializers.CharField(source="get_status_display", read_only=True)
    changed_by_phone = serializers.CharField(source="changed_by.phone", read_only=True)

    class Meta:
        model = ParcelStatusHistory
        fields = ("id", "status", "status_display_name", "comment", "changed_by", "changed_by_phone", "created_at")
