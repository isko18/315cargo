from rest_framework import serializers

from .models import DeliveryAddress


class DeliveryAddressSerializer(serializers.ModelSerializer):
    """Глобальный адрес доставки (Китай/PDD).

    Пишут только структурные поля (супер-владелец). На чтение дополнительно
    отдаём имя получателя и готовую строку с уже вшитым кодом ТЕКУЩЕГО клиента —
    мобильное приложение подставляет это прямо в PDD (智能填写).
    """

    region = serializers.CharField(source="region_line", read_only=True)
    recipient = serializers.SerializerMethodField()
    one_line = serializers.SerializerMethodField()
    client_code = serializers.SerializerMethodField()

    class Meta:
        model = DeliveryAddress
        fields = (
            "recipient_name",
            "phone",
            "province",
            "city",
            "district",
            "detail_address",
            "postal_code",
            "instructions",
            "is_active",
            "region",
            "recipient",
            "one_line",
            "client_code",
            "updated_at",
        )
        read_only_fields = ("updated_at",)

    def _client_code(self):
        user = getattr(self.context.get("request"), "user", None)
        return getattr(user, "client_code", "") or ""

    def get_client_code(self, obj):
        return self._client_code()

    def get_recipient(self, obj):
        return obj.recipient_with_code(self._client_code())

    def get_one_line(self, obj):
        return obj.one_line(self._client_code())
