from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Order(models.Model):
    class Source(models.TextChoices):
        PINDUODUO = "pinduoduo", _("Pinduoduo")
        TAOBAO = "taobao", _("Taobao")
        SHOP_1688 = "1688", _("1688")
        MANUAL = "manual", _("Вручную")

    class Status(models.TextChoices):
        CREATED = "created", _("Оформлен")
        PAID = "paid", _("Оплачен")
        PURCHASED = "purchased", _("Выкуплен")
        WAITING_CHINA_WAREHOUSE = "waiting_china_warehouse", _("Ожидается на складе в Китае")
        ARRIVED_CHINA_WAREHOUSE = "arrived_china_warehouse", _("Прибыл на склад в Китае")
        CANCELLED = "cancelled", _("Отменён")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders",
        verbose_name=_("Клиент"),
    )
    source = models.CharField(
        _("Источник"), max_length=32, choices=Source.choices, default=Source.MANUAL
    )
    external_order_id = models.CharField(_("Номер заказа у поставщика"), max_length=128, blank=True)
    product_url = models.URLField(_("Ссылка на товар"), blank=True)
    product_title = models.CharField(_("Название товара"), max_length=255, blank=True)
    price = models.DecimalField(_("Стоимость"), max_digits=12, decimal_places=2, null=True, blank=True)
    quantity = models.PositiveIntegerField(_("Количество"), default=1)
    status = models.CharField(
        _("Статус"), max_length=64, choices=Status.choices, default=Status.CREATED
    )
    track_number = models.CharField(_("Трек-номер"), max_length=128, blank=True, db_index=True)
    raw_data = models.JSONField(_("Сырые данные"), default=dict, blank=True)
    created_at = models.DateTimeField(_("Создан"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Обновлён"), auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("Заказ")
        verbose_name_plural = _("Заказы")

    def __str__(self):
        return f"{self.user.phone} {self.product_title or self.external_order_id or self.id}"
