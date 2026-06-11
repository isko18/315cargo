from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class CityDeliveryTariff(models.Model):
    title = models.CharField(_("Название"), max_length=255)
    base_price = models.DecimalField(
        _("Базовая стоимость"), max_digits=12, decimal_places=2
    )
    price_per_kg = models.DecimalField(
        _("Цена за кг"), max_digits=12, decimal_places=2, default=0
    )
    free_weight_kg = models.DecimalField(
        _("Бесплатный вес, кг"),
        max_digits=10,
        decimal_places=3,
        default=0,
        help_text=_("Вес, до которого взимается только базовая стоимость"),
    )
    min_price = models.DecimalField(
        _("Минимальная стоимость"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    is_default = models.BooleanField(_("По умолчанию"), default=False)
    is_active = models.BooleanField(_("Активен"), default=True)
    cargo = models.ForeignKey(
        "cargo.CargoCompany",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="city_delivery_tariffs",
        verbose_name=_("Карго-центр"),
        help_text=_(
            "Карго, к которому относится тариф. Для общего тарифа (без ПВЗ) "
            "ограничивает выбор этим карго."
        ),
    )
    pickup_point = models.ForeignKey(
        "pickup_points.PickupPoint",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="city_delivery_tariffs",
        verbose_name=_("ПВЗ"),
        help_text=_("Если задано — тариф применяется только к посылкам этого ПВЗ"),
    )
    created_at = models.DateTimeField(_("Создан"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Обновлён"), auto_now=True)

    class Meta:
        ordering = ("-is_default", "title")
        verbose_name = _("Тариф доставки по городу")
        verbose_name_plural = _("Тарифы доставки по городу")

    def __str__(self):
        return self.title

    def calculate(self, weight_kg=None):
        from decimal import Decimal

        def _to_decimal(value):
            if value in (None, ""):
                return Decimal("0")
            return value if isinstance(value, Decimal) else Decimal(str(value))

        weight = _to_decimal(weight_kg)
        free_weight = _to_decimal(self.free_weight_kg)
        base = _to_decimal(self.base_price)
        per_kg = _to_decimal(self.price_per_kg)
        billable = max(Decimal("0"), weight - free_weight)
        price = base + billable * per_kg
        if self.min_price and price < _to_decimal(self.min_price):
            price = _to_decimal(self.min_price)
        return price


class CityDeliveryRequest(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", _("Создана")
        PRICE_CALCULATED = "price_calculated", _("Стоимость рассчитана")
        ACCEPTED = "accepted", _("Принята")
        ASSIGNED_TO_COURIER = "assigned_to_courier", _("Назначен курьер")
        IN_DELIVERY = "in_delivery", _("В доставке")
        DELIVERED = "delivered", _("Доставлена")
        CANCELLED = "cancelled", _("Отменена")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="city_delivery_requests",
        verbose_name=_("Клиент"),
    )
    parcel = models.ForeignKey(
        "parcels.Parcel",
        on_delete=models.CASCADE,
        related_name="city_delivery_requests",
        verbose_name=_("Посылка"),
    )
    tariff = models.ForeignKey(
        CityDeliveryTariff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requests",
        verbose_name=_("Тариф"),
    )
    courier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="courier_city_deliveries",
        verbose_name=_("Курьер"),
    )
    address = models.TextField(_("Адрес доставки"))
    recipient_name = models.CharField(_("Имя получателя"), max_length=255)
    recipient_phone = models.CharField(_("Телефон получателя"), max_length=32)
    comment = models.TextField(_("Комментарий"), blank=True)
    price = models.DecimalField(
        _("Стоимость"), max_digits=12, decimal_places=2, null=True, blank=True
    )
    status = models.CharField(
        _("Статус"), max_length=32, choices=Status.choices, default=Status.CREATED
    )
    delivery_date = models.DateField(_("Дата доставки"), null=True, blank=True)
    delivery_time_slot = models.CharField(
        _("Желаемое время"), max_length=64, blank=True
    )
    delivered_at = models.DateTimeField(_("Доставлено"), null=True, blank=True)
    created_at = models.DateTimeField(_("Создана"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Обновлена"), auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("Заявка на доставку по городу")
        verbose_name_plural = _("Заявки на доставку по городу")

    def __str__(self):
        return f"{self.parcel.track_number} {self.status}"
