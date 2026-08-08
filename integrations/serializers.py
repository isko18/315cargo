from rest_framework import serializers

from .models import MarketplaceAccount


class MarketplaceAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketplaceAccount
        fields = (
            "marketplace",
            "is_connected",
            "external_user_id",
            "last_sync_at",
            "last_sync_error",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class MarketplaceConnectSerializer(serializers.Serializer):
    session_data = serializers.JSONField(required=False)


class MarketplaceOrderPayloadSerializer(serializers.Serializer):
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


class MarketplaceWebhookSerializer(serializers.Serializer):
    client_code = serializers.CharField()
    orders = MarketplaceOrderPayloadSerializer(many=True)


class MarketplaceIngestSerializer(serializers.Serializer):
    """Заказы из WebView. Принимаем СЫРЫЕ объекты ответа маркетплейса —
    разбор (цена/статус/фильтр) делается на сервере, чтобы правки не требовали
    пересборки приложения."""

    orders = serializers.ListField(
        child=serializers.DictField(), allow_empty=True
    )
