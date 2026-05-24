from django.db import models
from django.utils.translation import gettext_lazy as _


class PickupPoint(models.Model):
    cargo = models.ForeignKey(
        "cargo.CargoCompany",
        on_delete=models.CASCADE,
        related_name="pickup_points",
        verbose_name=_("Карго-центр"),
    )
    title = models.CharField(_("Название"), max_length=255)
    address = models.TextField(_("Адрес"))
    phone = models.CharField(_("Контактный телефон"), max_length=32, blank=True)
    work_schedule = models.CharField(_("График работы"), max_length=255, blank=True)
    is_active = models.BooleanField(_("Активен"), default=True)
    created_at = models.DateTimeField(_("Создан"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Обновлён"), auto_now=True)

    class Meta:
        ordering = ("title",)
        verbose_name = _("ПВЗ")
        verbose_name_plural = _("ПВЗ")

    def __str__(self):
        return self.title
