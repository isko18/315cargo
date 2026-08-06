from rest_framework import serializers

from .models import DeliveryAddress


class DeliveryAddressSerializer(serializers.ModelSerializer):
    """Глобальный адрес доставки (Китай/PDD).

    Пишут только структурные поля (супер-владелец). На чтение дополнительно
    отдаём имя получателя и готовую строку, где в конце адреса уже стоят код
    карго и код ТЕКУЩЕГО клиента — мобильное приложение подставляет это прямо
    в PDD (智能填写).
    """

    region = serializers.CharField(source="region_line", read_only=True)
    detail_address_full = serializers.SerializerMethodField()
    recipient = serializers.SerializerMethodField()
    one_line = serializers.SerializerMethodField()
    client_code = serializers.SerializerMethodField()
    cargo_code = serializers.SerializerMethodField()

    class Meta:
        model = DeliveryAddress
        fields = (
            "recipient_name",
            "phone",
            "province",
            "city",
            "district",
            "detail_address",
            "detail_address_full",
            "instructions",
            "is_active",
            "region",
            "recipient",
            "one_line",
            "client_code",
            "cargo_code",
            "updated_at",
        )
        read_only_fields = ("updated_at",)

    def _client_code(self):
        user = getattr(self.context.get("request"), "user", None)
        return getattr(user, "client_code", "") or ""

    def _cargo(self):
        user = getattr(self.context.get("request"), "user", None)
        return getattr(user, "cargo", None)

    def _cargo_code(self):
        return getattr(self._cargo(), "code", "") or ""

    def _cargo_recipient(self):
        """ФИО получателя карго клиента — у каждого карго свой человек в Китае."""
        return getattr(self._cargo(), "recipient_name", "") or ""

    def _address_suffix(self):
        """Приписка к адресу склада — у каждого карго своя ячейка."""
        return getattr(self._cargo(), "address_suffix", "") or ""

    def get_detail_address_full(self, obj):
        """Детальный адрес вместе с припиской карго — для ручного заполнения."""
        return obj.detail_for(self._address_suffix())

    def get_client_code(self, obj):
        return self._client_code()

    def get_cargo_code(self, obj):
        return self._cargo_code()

    def get_recipient(self, obj):
        return obj.recipient_for(self._client_code(), self._cargo_recipient())

    def get_one_line(self, obj):
        return obj.one_line(
            client_code=self._client_code(),
            cargo_code=self._cargo_code(),
            cargo_recipient=self._cargo_recipient(),
            address_suffix=self._address_suffix(),
        )
