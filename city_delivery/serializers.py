from django.db.models import Q
from rest_framework import serializers

from parcels.models import Parcel

from .models import CityDeliveryPoint, CityDeliveryRequest, CityDeliveryTariff


class CityDeliveryTariffSerializer(serializers.ModelSerializer):
    # default=None обязателен: без него DRF, упёршись в пустой pickup_point при
    # обходе source, выбрасывает поле из ответа целиком — оно есть в схеме, а в
    # payload его нет, и клиент спотыкается на отсутствующем ключе.
    pickup_point_title = serializers.CharField(
        source="pickup_point.title", read_only=True, default=None
    )

    class Meta:
        model = CityDeliveryTariff
        fields = (
            "id",
            "title",
            "base_price",
            "price_per_kg",
            "free_weight_kg",
            "min_price",
            "is_default",
            "is_active",
            "cargo",
            "pickup_point",
            "pickup_point_title",
        )


class ManagedCityDeliveryTariffSerializer(serializers.ModelSerializer):
    """CRUD тарифов для владельца карго. ``cargo`` проставляется во view."""

    class Meta:
        model = CityDeliveryTariff
        fields = (
            "id",
            "title",
            "base_price",
            "price_per_kg",
            "free_weight_kg",
            "min_price",
            "is_default",
            "is_active",
            "cargo",
            "pickup_point",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "cargo", "created_at", "updated_at")

    def validate_pickup_point(self, pickup_point):
        request = self.context.get("request")
        if (
            pickup_point is not None
            and request is not None
            and not request.user.is_superuser
            and pickup_point.cargo_id != request.user.cargo_id
        ):
            raise serializers.ValidationError("ПВЗ принадлежит другому карго-центру")
        return pickup_point


class CityDeliveryParcelSerializer(serializers.ModelSerializer):
    """Посылка внутри заявки — столько, сколько нужно экрану заявки."""

    status_display_name = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Parcel
        fields = ("id", "track_number", "status", "status_display_name", "weight")
        read_only_fields = fields


class CityDeliveryPointSerializer(serializers.ModelSerializer):
    """Точка доставки для клиента. Цены нет: доставка бесплатная."""

    clients_count = serializers.IntegerField(
        read_only=True,
        default=0,
        help_text="Сколько клиентов уже возят сюда — подсказка при выборе.",
    )

    class Meta:
        model = CityDeliveryPoint
        fields = ("id", "title", "address", "work_hours", "is_active", "clients_count")
        read_only_fields = fields


class ManagedCityDeliveryPointSerializer(serializers.ModelSerializer):
    """Точка в панели: CRUD плюс статистика. ``cargo`` проставляется во view."""

    clients_count = serializers.IntegerField(
        read_only=True, default=0, help_text="Разных клиентов с заявками на точку."
    )
    active_requests = serializers.IntegerField(
        read_only=True, default=0, help_text="Заявок в работе: не доставлены и не отменены."
    )
    delivered_count = serializers.IntegerField(
        read_only=True, default=0, help_text="Доставлено заявок за всё время."
    )

    class Meta:
        model = CityDeliveryPoint
        fields = (
            "id",
            "title",
            "address",
            "work_hours",
            "is_active",
            "position",
            "clients_count",
            "active_requests",
            "delivered_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class CityDeliveryRequestSerializer(serializers.ModelSerializer):
    """Заявка клиента в ответе.

    ``parcel``, ``track_number``, ``address``, ``price`` и ``tariff_title`` —
    для установленных версий приложения; новые читают ``parcels`` и
    ``delivery_point``.
    """

    status_display_name = serializers.CharField(source="get_status_display", read_only=True)
    tariff_title = serializers.CharField(source="tariff.title", read_only=True, default=None)
    track_number = serializers.CharField(
        source="parcel.track_number", read_only=True, default=None
    )
    delivery_point_title = serializers.CharField(
        source="delivery_point.title", read_only=True, default=None
    )
    parcels = CityDeliveryParcelSerializer(many=True, read_only=True)
    parcels_count = serializers.IntegerField(read_only=True)
    total_weight_kg = serializers.DecimalField(
        max_digits=12, decimal_places=3, read_only=True
    )

    class Meta:
        model = CityDeliveryRequest
        fields = (
            "id",
            "user",
            "delivery_point",
            "delivery_point_title",
            "suggested_point",
            "address",
            "is_standing",
            "parcels",
            "parcels_count",
            "total_weight_kg",
            "parcel",
            "track_number",
            "tariff",
            "tariff_title",
            "price",
            "recipient_name",
            "recipient_phone",
            "comment",
            "status",
            "status_display_name",
            "delivery_date",
            "delivery_time_slot",
            "delivered_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class CityDeliveryRequestWriteSerializer(serializers.Serializer):
    """Тело POST/PATCH заявки клиента.

    Куда — одно из трёх: ``delivery_point`` (точка из справочника),
    ``suggested_point`` (своя, оператор согласует) или ``address`` (старые
    версии). Посылки — ``parcels`` целиком; без них заявка постоянная.
    """

    _FINAL_PARCEL_STATUSES = {
        Parcel.Status.ISSUED,
        Parcel.Status.DELIVERED,
        Parcel.Status.CANCELLED,
    }

    parcels = serializers.PrimaryKeyRelatedField(
        many=True,
        required=False,
        queryset=Parcel.objects.none(),
        help_text="ID посылок, весь состав. Пусто или нет поля — постоянная "
        "заявка: всё, что лежит и придёт в ПВЗ.",
    )
    parcel = serializers.PrimaryKeyRelatedField(
        required=False,
        allow_null=True,
        queryset=Parcel.objects.none(),
        help_text="Устарело: одна посылка, добавляется к уже выбранным.",
    )
    delivery_point = serializers.PrimaryKeyRelatedField(
        required=False,
        allow_null=True,
        queryset=CityDeliveryPoint.objects.none(),
        help_text="Точка из GET /api/city-delivery-points/.",
        error_messages={"does_not_exist": "Такой точки нет или она закрыта"},
    )
    suggested_point = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        help_text="Своя точка, если подходящей в списке нет.",
    )
    address = serializers.CharField(
        required=False, allow_blank=True, help_text="Устарело: свободный адрес."
    )
    is_standing = serializers.BooleanField(
        required=False,
        help_text="Постоянная заявка явно. По умолчанию — когда посылок нет.",
    )
    recipient_name = serializers.CharField(max_length=255)
    recipient_phone = serializers.CharField(max_length=32)
    comment = serializers.CharField(required=False, allow_blank=True)
    delivery_date = serializers.DateField(required=False, allow_null=True)
    delivery_time_slot = serializers.CharField(
        required=False, allow_blank=True, max_length=64
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is None or request.user.is_anonymous:
            return
        user = request.user
        own = Parcel.objects.filter(user=user)
        self.fields["parcels"].child_relation.queryset = own
        self.fields["parcel"].queryset = own
        self.fields["delivery_point"].queryset = CityDeliveryPoint.objects.filter(
            cargo_id=user.cargo_id, is_active=True
        )

    def _check_parcel(self, parcel):
        from .services import CLOSED_STATUSES, EDITABLE_STATUSES

        if parcel.status in self._FINAL_PARCEL_STATUSES:
            raise serializers.ValidationError(
                f"Посылка {parcel.track_number} уже выдана или отменена"
            )
        on_the_road = CityDeliveryRequest.objects.filter(
            Q(parcels=parcel) | Q(parcel=parcel)
        ).exclude(status__in=(*CLOSED_STATUSES, *EDITABLE_STATUSES))
        if self.instance is not None:
            on_the_road = on_the_road.exclude(pk=self.instance.pk)
        if on_the_road.exists():
            raise serializers.ValidationError(
                f"Посылка {parcel.track_number} уже едет с курьером"
            )
        return parcel

    def validate_parcels(self, parcels):
        return [self._check_parcel(p) for p in parcels]

    def validate_parcel(self, parcel):
        return self._check_parcel(parcel) if parcel else parcel

    def validate(self, attrs):
        if not self.partial and not (
            attrs.get("delivery_point")
            or (attrs.get("suggested_point") or "").strip()
            or (attrs.get("address") or "").strip()
        ):
            raise serializers.ValidationError(
                {"delivery_point": "Укажите, куда везти: точку из списка или свою"}
            )
        return attrs


class ManagedCityDeliveryRequestSerializer(serializers.ModelSerializer):
    """Заявка в панели: оператор меняет статус, курьера, дату и точку."""

    status_display_name = serializers.CharField(source="get_status_display", read_only=True)
    track_number = serializers.CharField(
        source="parcel.track_number", read_only=True, default=None
    )
    client_name = serializers.CharField(source="user.full_name", read_only=True)
    client_phone = serializers.CharField(source="user.phone", read_only=True)
    client_code = serializers.CharField(source="user.client_code", read_only=True)
    tariff_title = serializers.CharField(source="tariff.title", read_only=True, default=None)
    delivery_point_title = serializers.CharField(
        source="delivery_point.title", read_only=True, default=None
    )
    parcels = CityDeliveryParcelSerializer(many=True, read_only=True)
    parcels_count = serializers.IntegerField(read_only=True)
    total_weight_kg = serializers.DecimalField(
        max_digits=12, decimal_places=3, read_only=True
    )

    class Meta:
        model = CityDeliveryRequest
        fields = (
            "id",
            "user",
            "client_name",
            "client_phone",
            "client_code",
            "delivery_point",
            "delivery_point_title",
            "suggested_point",
            "address",
            "is_standing",
            "parcels",
            "parcels_count",
            "total_weight_kg",
            "parcel",
            "track_number",
            "tariff",
            "tariff_title",
            "recipient_name",
            "recipient_phone",
            "comment",
            "price",
            "status",
            "status_display_name",
            "delivery_date",
            "delivery_time_slot",
            "delivered_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "user",
            "is_standing",
            "parcel",
            "track_number",
            "tariff",
            "price",
            "status_display_name",
            "delivered_at",
            "created_at",
            "updated_at",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and not user.is_superuser:
            self.fields["delivery_point"].queryset = CityDeliveryPoint.objects.filter(
                cargo_id=request.user.cargo_id
            )

    def validate(self, attrs):
        # Оператор перевёл предложение в точку — предложение обработано.
        if attrs.get("delivery_point") and "suggested_point" not in attrs:
            attrs["suggested_point"] = ""
        return attrs


class CityDeliverySuggestionSerializer(serializers.Serializer):
    text = serializers.CharField(help_text="Самое частое написание у клиентов.")
    clients_count = serializers.IntegerField()
    requests_count = serializers.IntegerField()
    request_ids = serializers.ListField(child=serializers.IntegerField())
    first_seen = serializers.DateTimeField()
    last_seen = serializers.DateTimeField()


class AdoptSuggestionsRequestSerializer(serializers.Serializer):
    text = serializers.CharField(
        help_text="Предложение, как в suggestions/. Сравнивается без регистра "
        "и лишних пробелов."
    )


class AdoptSuggestionsResponseSerializer(serializers.Serializer):
    updated = serializers.IntegerField(help_text="Сколько заявок переведено в точку.")


class CityDeliveryConflictSerializer(serializers.Serializer):
    detail = serializers.CharField()
    id = serializers.IntegerField(help_text="Живая заявка клиента — открыть её.")


class CityDeliveryEstimateRequestSerializer(serializers.Serializer):
    parcel = serializers.IntegerField(required=False, help_text="Устарело: ID одной посылки")
    parcels = serializers.ListField(
        child=serializers.IntegerField(), required=False, help_text="ID посылок"
    )


class CityDeliveryEstimateResponseSerializer(serializers.Serializer):
    parcel = serializers.IntegerField(allow_null=True)
    parcels = serializers.ListField(child=serializers.IntegerField())
    weight = serializers.DecimalField(max_digits=10, decimal_places=3, allow_null=True)
    price = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    tariff = CityDeliveryTariffSerializer(allow_null=True)
