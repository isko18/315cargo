from rest_framework import serializers

from .models import Shop
from .services import build_shop_open_url


class ShopSerializer(serializers.ModelSerializer):
    open_url = serializers.SerializerMethodField()
    client_code = serializers.SerializerMethodField()
    instruction = serializers.SerializerMethodField()

    class Meta:
        model = Shop
        fields = ("id", "title", "slug", "icon", "open_url", "open_type", "client_code", "instruction")

    def get_open_url(self, obj):
        return build_shop_open_url(obj, self.context["request"].user)

    def get_client_code(self, obj):
        if obj.client_code_strategy == Shop.ClientCodeStrategy.CLIPBOARD:
            return self.context["request"].user.client_code
        return None

    def get_instruction(self, obj):
        if obj.client_code_strategy == Shop.ClientCodeStrategy.MANUAL_INSTRUCTION:
            return f"Use client code {self.context['request'].user.client_code} when placing an order."
        if obj.client_code_strategy == Shop.ClientCodeStrategy.CLIPBOARD:
            return "Copy client code and paste it in the shop order comment."
        return None
