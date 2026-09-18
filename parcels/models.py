from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Parcel(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", _("Оформлен")
        PURCHASED = "purchased", _("Выкуплен")
        WAITING_CHINA_WAREHOUSE = "waiting_china_warehouse", _("Ожидается на складе в Китае")
        ARRIVED_CHINA_WAREHOUSE = "arrived_china_warehouse", _("Прибыл на склад в Китае")
        IN_STORAGE = "in_storage", _("Отправлен на хранение")
        SENT_TO_KYRGYZSTAN = "sent_to_kyrgyzstan", _("Отправлен со склада, в пути")
        IN_TRANSIT = "in_transit", _("В пути")
        ARRIVED_KYRGYZSTAN = "arrived_kyrgyzstan", _("Прибыл в Кыргызстан")
        PROCESSING = "processing", _("Классификация и обработка")
        ARRIVED_TOPA = "arrived_topa", _("Прибыл в Топа")
        AT_PICKUP_POINT = "at_pickup_point", _("Прибыл в пункт выдачи")
        CITY_DELIVERY = "city_delivery", _("Передан на доставку по городу")
        DELIVERED = "delivered", _("Доставлен")
        ISSUED = "issued", _("Выдан клиенту")
        CANCELLED = "cancelled", _("Отменён")

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", _("Не оплачен")
        PARTIAL = "partial", _("Частично оплачен")
        PAID = "paid", _("Оплачен")

    class ReceiptMethod(models.TextChoices):
        PICKUP = "pickup", _("Самовывоз из ПВЗ")
        CITY_DELIVERY = "city_delivery", _("Доставка по городу")

    cargo = models.ForeignKey(
        "cargo.CargoCompany",
        on_delete=models.PROTECT,
        related_name="parcels",
        null=True,
        blank=True,
        verbose_name=_("Карго-центр"),
        help_text=_("Может быть пустым для «ничьих» посылок со склада в Китае до привязки к клиенту."),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="parcels",
        verbose_name=_("Клиент"),
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="parcels",
        verbose_name=_("Заказ"),
    )
    pickup_point = models.ForeignKey(
        "pickup_points.PickupPoint",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="parcels",
        verbose_name=_("ПВЗ приёмки"),
        help_text=_("Физический пункт выдачи, где посылка принята (ставится при статусе «В ПВЗ»)."),
    )
    track_number = models.CharField(_("Трек-номер"), max_length=128, unique=True)
    client_code = models.CharField(_("Клиентский код"), max_length=16, db_index=True)
    status = models.CharField(
        _("Статус"), max_length=64, choices=Status.choices, default=Status.CREATED
    )
    location = models.CharField(_("Местоположение"), max_length=255, blank=True)
    weight = models.DecimalField(_("Вес, кг"), max_digits=10, decimal_places=3, null=True, blank=True)
    volume = models.DecimalField(_("Объём, м³"), max_digits=10, decimal_places=3, null=True, blank=True)
    delivery_price = models.DecimalField(
        _("Стоимость доставки"), max_digits=12, decimal_places=2, null=True, blank=True
    )
    # --- Карточка товара в панели ---
    # Габариты нужны отдельными числами, а не строкой: по ним считается объём
    # и рассчитывается место в машине.
    length_cm = models.DecimalField(
        _("Длина, см"), max_digits=8, decimal_places=1, null=True, blank=True
    )
    width_cm = models.DecimalField(
        _("Ширина, см"), max_digits=8, decimal_places=1, null=True, blank=True
    )
    height_cm = models.DecimalField(
        _("Высота, см"), max_digits=8, decimal_places=1, null=True, blank=True
    )
    payment_status = models.CharField(
        _("Статус оплаты"), max_length=16, choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID, db_index=True,
    )
    receipt_method = models.CharField(
        _("Способ получения"), max_length=16, choices=ReceiptMethod.choices,
        default=ReceiptMethod.PICKUP,
    )
    delivery_address = models.TextField(
        _("Адрес доставки"), blank=True,
        help_text=_("Заполняется при доставке по городу."),
    )
    usd_rate = models.DecimalField(
        _("Курс USD"), max_digits=10, decimal_places=4, null=True, blank=True,
        help_text=_("Курс на момент расчёта: потом он меняется, а счёт клиента — нет."),
    )
    client_price = models.DecimalField(
        _("Цена клиенту"), max_digits=12, decimal_places=2, null=True, blank=True,
        help_text=_(
            "Итоговая сумма к оплате. Отличается от расчёта по тарифу, когда были "
            "обрешётка, упаковка или своя договорённость."
        ),
    )
    crating = models.BooleanField(_("Обрешётка"), default=False)
    packaging = models.BooleanField(_("Упаковка"), default=False)
    notified_at = models.DateTimeField(
        _("Уведомление отправлено"), null=True, blank=True,
        help_text=_("Когда клиенту ушло последнее уведомление о статусе."),
    )
    arrived_at = models.DateTimeField(_("Дата поступления"), null=True, blank=True)
    issued_at = models.DateTimeField(_("Дата выдачи"), null=True, blank=True)
    is_archived = models.BooleanField(_("В архиве"), default=False, db_index=True)
    created_at = models.DateTimeField(_("Создан"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Обновлён"), auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("Посылка")
        verbose_name_plural = _("Посылки")

    ARRIVED_STATUSES = (Status.ARRIVED_CHINA_WAREHOUSE, Status.ARRIVED_KYRGYZSTAN)

    def __str__(self):
        return self.track_number

    def apply_status_timestamps(self):
        """Stamp arrived_at / issued_at from the current status (idempotent).

        Returns the list of field names that changed so callers using
        ``save(update_fields=...)`` can include them.
        """
        from django.utils import timezone

        changed = []
        if self.status in self.ARRIVED_STATUSES and self.arrived_at is None:
            self.arrived_at = timezone.now()
            changed.append("arrived_at")
        if self.status == self.Status.ISSUED and self.issued_at is None:
            self.issued_at = timezone.now()
            changed.append("issued_at")
        return changed


class ParcelStatusHistory(models.Model):
    parcel = models.ForeignKey(
        Parcel, on_delete=models.CASCADE, related_name="history", verbose_name=_("Посылка")
    )
    status = models.CharField(_("Статус"), max_length=64, choices=Parcel.Status.choices)
    comment = models.TextField(_("Комментарий"), blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="parcel_status_changes",
        verbose_name=_("Кто изменил"),
    )
    created_at = models.DateTimeField(_("Дата изменения"), auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("История статуса посылки")
        verbose_name_plural = _("История статусов посылок")
        indexes = [
            # История операций всегда читается «свежие сверху» с фильтром по
            # статусу (приём / выдача / Китай) — без индекса это скан таблицы,
            # которая растёт на каждую смену статуса каждой посылки.
            models.Index(fields=["status", "-created_at"], name="psh_status_created_idx"),
            # Оператор видит только свои операции.
            models.Index(fields=["changed_by", "-created_at"], name="psh_actor_created_idx"),
        ]

    def __str__(self):
        return f"{self.parcel.track_number} {self.status}"
