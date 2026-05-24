from django.db import models
from django.utils.translation import gettext_lazy as _


class CargoCompany(models.Model):
    title = models.CharField(_("Название"), max_length=255)
    slug = models.SlugField(_("Идентификатор"), unique=True)
    description = models.TextField(_("Описание"), blank=True)
    logo = models.ImageField(_("Логотип"), upload_to="cargo_logos/", null=True, blank=True)
    phone = models.CharField(_("Телефон"), max_length=32, blank=True)
    address = models.TextField(_("Адрес"), blank=True)
    is_active = models.BooleanField(_("Активен"), default=True)
    created_at = models.DateTimeField(_("Создан"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Обновлён"), auto_now=True)

    class Meta:
        ordering = ("title",)
        verbose_name = _("Карго-центр")
        verbose_name_plural = _("Карго-центры")

    def __str__(self):
        return self.title
