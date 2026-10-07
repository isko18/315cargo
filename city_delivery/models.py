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


class CityDeliveryPoint(models.Model):
    """Точка выдачи для доставки по городу: куда курьер везёт посылки клиента.

    Раньше шесть точек были зашиты в коде приложения, и поменять их можно было
    только выпуском новой версии в сторы. У каждого карго свои точки.
    """

    cargo = models.ForeignKey(
        "cargo.CargoCompany",
        on_delete=models.CASCADE,
        related_name="city_delivery_points",
        verbose_name=_("Карго-центр"),
    )
    title = models.CharField(_("Название"), max_length=255)
    address = models.CharField(_("Уточнение адреса"), max_length=255, blank=True)
    work_hours = models.CharField(_("Часы работы"), max_length=64, blank=True)
    is_active = models.BooleanField(
        _("Активна"),
        default=True,
        help_text=_("Неактивная точка не показывается клиенту, но остаётся в истории заявок"),
    )
    position = models.PositiveIntegerField(_("Порядок"), default=0)
    created_at = models.DateTimeField(_("Создана"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Обновлена"), auto_now=True)

    class Meta:
        ordering = ("position", "title")
        verbose_name = _("Точка доставки по городу")
        verbose_name_plural = _("Точки доставки по городу")

    def __str__(self):
        return self.title


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
    # Старое поле «одна посылка». Живёт ради установленных версий приложения,
    # которые читают parcel и track_number; держится равным первой посылке из
    # parcels. SET_NULL, а не CASCADE: удаление одной посылки не должно уносить
    # заявку с остальными.
    parcel = models.ForeignKey(
        "parcels.Parcel",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="city_delivery_requests",
        verbose_name=_("Посылка (старое поле)"),
    )
    # Заявка — на клиента, а не на посылку: курьер едет один раз за всеми.
    parcels = models.ManyToManyField(
        "parcels.Parcel",
        blank=True,
        related_name="city_deliveries",
        verbose_name=_("Посылки"),
    )
    delivery_point = models.ForeignKey(
        CityDeliveryPoint,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="requests",
        verbose_name=_("Точка выдачи"),
    )
    suggested_point = models.CharField(
        _("Предложенная клиентом точка"),
        max_length=255,
        blank=True,
        help_text=_("Просьба, а не готовый адрес: оператор согласует и заводит точку"),
    )
    is_standing = models.BooleanField(
        _("Постоянная"),
        default=False,
        help_text=_(
            "Оформлена без посылок: «всё моё везите сюда». Подхватывает посылки, "
            "приходящие в ПВЗ, а после доставки открывается заново"
        ),
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
    # Свободный адрес — для старых версий приложения; новые шлют точку.
    address = models.TextField(_("Адрес доставки"), blank=True)
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
        return f"#{self.pk} {self.destination} {self.status}"

    @property
    def destination(self):
        """Куда везти — одной строкой, для уведомлений и админки."""
        if self.delivery_point_id:
            return self.delivery_point.title
        return self.suggested_point or self.address or "—"

    # Считаются по parcels.all(), а не запросом: во views parcels подгружены
    # prefetch-ем, и список заявок не делает лишних запросов на строку.
    @property
    def parcels_count(self):
        return len(self.parcels.all())

    @property
    def total_weight_kg(self):
        from decimal import Decimal

        return sum((p.weight or Decimal("0")) for p in self.parcels.all()) or Decimal("0")
