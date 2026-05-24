from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class PinduoduoAccount(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pinduoduo_account",
        verbose_name=_("Клиент"),
    )
    is_connected = models.BooleanField(_("Подключён"), default=False)
    external_user_id = models.CharField(_("ID на стороне Pinduoduo"), max_length=128, blank=True)
    session_data = models.JSONField(_("Данные сессии"), default=dict, blank=True)
    last_sync_at = models.DateTimeField(_("Последняя синхронизация"), null=True, blank=True)
    last_sync_error = models.TextField(_("Последняя ошибка"), blank=True)
    created_at = models.DateTimeField(_("Создан"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Обновлён"), auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("Аккаунт Pinduoduo")
        verbose_name_plural = _("Аккаунты Pinduoduo")

    def __str__(self):
        return f"{self.user.phone} Pinduoduo"
