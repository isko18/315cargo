from rest_framework import serializers

from .models import Parcel, ParcelStatusHistory


class ParcelSerializer(serializers.ModelSerializer):
    status_display_name = serializers.CharField(source="get_status_display", read_only=True)
    # Карточка посылки: данные товара берём из связанного заказа.
    product_title = serializers.SerializerMethodField()
    product_price = serializers.SerializerMethodField()
    product_image = serializers.SerializerMethodField()
    # Клиент — для детального просмотра на складе.
    client_name = serializers.CharField(source="user.full_name", read_only=True, default=None)
    client_phone = serializers.CharField(source="user.phone", read_only=True, default=None)
    # ПВЗ приёмки (физический) в приоритете; иначе — ПВЗ клиента (адресат).
    pickup_point_title = serializers.SerializerMethodField()

    def get_pickup_point_title(self, obj):
        if obj.pickup_point_id:
            return obj.pickup_point.title
        user_pp = getattr(obj.user, "pickup_point", None) if obj.user_id else None
        return user_pp.title if user_pp else None

    def get_product_title(self, obj):
        return obj.order.product_title if obj.order_id else None

    def get_product_price(self, obj):
        return obj.order.price if obj.order_id else None

    def get_product_image(self, obj):
        raw = getattr(obj.order, "raw_data", None) if obj.order_id else None
        goods = raw.get("order_goods") if isinstance(raw, dict) else None
        if isinstance(goods, list) and goods and isinstance(goods[0], dict):
            return goods[0].get("thumb_url") or goods[0].get("hd_thumb_url")
        return None

    class Meta:
        model = Parcel
        fields = (
            "id",
            "cargo",
            "user",
            "order",
            "track_number",
            "client_code",
            "client_name",
            "client_phone",
            "pickup_point_title",
            "status",
            "status_display_name",
            "product_title",
            "product_price",
            "product_image",
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
    weight = serializers.DecimalField(
        max_digits=10, decimal_places=3, min_value=0, required=False, allow_null=True
    )
    # Код клиента — для ручного приёма товара без заказа (склад в Китае).
    client_code = serializers.CharField(
        max_length=16, required=False, allow_blank=True
    )
    # ПВЗ приёмки — чтобы при статусе «В ПВЗ» записать его адрес в location.
    pickup_point = serializers.IntegerField(required=False, allow_null=True)


class ParcelAssignSerializer(serializers.Serializer):
    client_code = serializers.CharField(max_length=16)


class ParcelWeightSerializer(serializers.Serializer):
    """Задать/уточнить вес посылки (приём и выдача) с пересчётом стоимости."""

    weight = serializers.DecimalField(
        max_digits=10, decimal_places=3, min_value=0, allow_null=True
    )


class OperationHistorySerializer(serializers.ModelSerializer):
    """Строка истории операций приём/выдача (из ParcelStatusHistory)."""

    type = serializers.SerializerMethodField()
    status_display_name = serializers.CharField(source="get_status_display", read_only=True)
    track_number = serializers.CharField(source="parcel.track_number", read_only=True)
    client_code = serializers.CharField(source="parcel.client_code", read_only=True, default="")
    client_name = serializers.CharField(source="parcel.user.full_name", read_only=True, default=None)
    product_title = serializers.SerializerMethodField()
    weight = serializers.DecimalField(
        source="parcel.weight", max_digits=10, decimal_places=3, read_only=True
    )
    delivery_price = serializers.DecimalField(
        source="parcel.delivery_price", max_digits=12, decimal_places=2, read_only=True
    )
    operator_name = serializers.CharField(source="changed_by.full_name", read_only=True, default=None)
    operator_phone = serializers.CharField(source="changed_by.phone", read_only=True, default=None)
    pickup_point_title = serializers.SerializerMethodField()

    class Meta:
        model = ParcelStatusHistory
        fields = (
            "id",
            "parcel",
            "type",
            "status",
            "status_display_name",
            "track_number",
            "client_code",
            "client_name",
            "product_title",
            "weight",
            "delivery_price",
            "operator_name",
            "operator_phone",
            "pickup_point_title",
            "created_at",
        )

    def get_type(self, obj):
        return "issue" if obj.status == Parcel.Status.ISSUED else "receive"

    def get_product_title(self, obj):
        order = getattr(obj.parcel, "order", None)
        return order.product_title if order else None

    def get_pickup_point_title(self, obj):
        pp = getattr(obj.parcel, "pickup_point", None)
        if pp is not None:
            return pp.title
        user = getattr(obj.parcel, "user", None)
        upp = getattr(user, "pickup_point", None) if user is not None else None
        return upp.title if upp else None


class ParcelStatusHistorySerializer(serializers.ModelSerializer):
    status_display_name = serializers.CharField(source="get_status_display", read_only=True)
    changed_by_phone = serializers.CharField(source="changed_by.phone", read_only=True)

    class Meta:
        model = ParcelStatusHistory
        fields = ("id", "status", "status_display_name", "comment", "changed_by", "changed_by_phone", "created_at")
