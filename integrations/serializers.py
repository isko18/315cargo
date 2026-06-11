from rest_framework import serializers

from .models import PinduoduoAccount


class PinduoduoAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = PinduoduoAccount
        fields = (
            "is_connected",
            "external_user_id",
            "last_sync_at",
            "last_sync_error",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class PinduoduoConnectSerializer(serializers.Serializer):
    session_data = serializers.JSONField(required=False)


class PinduoduoOrderPayloadSerializer(serializers.Serializer):
    external_order_id = serializers.CharField()
    product_url = serializers.URLField(required=False, allow_blank=True)
    product_title = serializers.CharField(required=False, allow_blank=True)
    price = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )
    quantity = serializers.IntegerField(required=False, default=1)
    status = serializers.CharField(required=False, allow_blank=True)
    track_number = serializers.CharField(required=False, allow_blank=True)
    raw = serializers.JSONField(required=False)


class PinduoduoWebhookSerializer(serializers.Serializer):
    client_code = serializers.CharField()
    orders = PinduoduoOrderPayloadSerializer(many=True)


class PinduoduoIngestSerializer(serializers.Serializer):
    """Заказы, перехваченные приложением клиента из WebView (путь B)."""

    orders = PinduoduoOrderPayloadSerializer(many=True)
