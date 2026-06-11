from rest_framework import serializers

from .models import Order


class OrderSerializer(serializers.ModelSerializer):
    status_display_name = serializers.CharField(source="get_status_display", read_only=True)
    source_display_name = serializers.CharField(source="get_source_display", read_only=True)
    # Declared explicitly so the partial UniqueConstraint on the model does not
    # make DRF treat external_order_id as a required field (manual orders omit it).
    external_order_id = serializers.CharField(
        required=False, allow_blank=True, max_length=128
    )

    class Meta:
        model = Order
        fields = (
            "id",
            "user",
            "source",
            "source_display_name",
            "external_order_id",
            "product_url",
            "product_title",
            "price",
            "quantity",
            "status",
            "status_display_name",
            "track_number",
            "raw_data",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "user", "created_at", "updated_at")


class ManualOrderSerializer(OrderSerializer):
    class Meta(OrderSerializer.Meta):
        read_only_fields = ("id", "user", "source", "status", "created_at", "updated_at")
