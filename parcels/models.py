from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Parcel(models.Model):
    class Status(models.TextChoices):
        CREATED = "created", _("Оформлен")
        PURCHASED = "purchased", _("Выкуплен")
        WAITING_CHINA_WAREHOUSE = "waiting_china_warehouse", _("Ожидается на складе в Китае")
        ARRIVED_CHINA_WAREHOUSE = "arrived_china_warehouse", _("Прибыл на склад в Китае")
        SENT_TO_KYRGYZSTAN = "sent_to_kyrgyzstan", _("Отправлен в Кыргызстан")
        ARRIVED_KYRGYZSTAN = "arrived_kyrgyzstan", _("Прибыл в Кыргызстан")
        AT_PICKUP_POINT = "at_pickup_point", _("В ПВЗ")
        CITY_DELIVERY = "city_delivery", _("Передан на доставку по городу")
        DELIVERED = "delivered", _("Доставлен")
        ISSUED = "issued", _("Выдан клиенту")
        CANCELLED = "cancelled", _("Отменён")

    cargo = models.ForeignKey(
        "cargo.CargoCompany",
        on_delete=models.PROTECT,
        related_name="parcels",
        verbose_name=_("Карго-центр"),
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
    arrived_at = models.DateTimeField(_("Дата поступления"), null=True, blank=True)
    issued_at = models.DateTimeField(_("Дата выдачи"), null=True, blank=True)
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

    def __str__(self):
        return f"{self.parcel.track_number} {self.status}"
