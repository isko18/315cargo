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
    # Сессия PDD живёт в WebView приложения; сервер её не использует, но обязан
    # знать, сколько она продержалась — иначе причину коротких сессий (одна
    # активная сессия на аккаунт, перезапуск приложения, бан) не отличить.
    session_started_at = models.DateTimeField(
        _("Сессия начата"), null=True, blank=True
    )
    session_expired_at = models.DateTimeField(
        _("Сессия истекла"), null=True, blank=True
    )
    last_expire_reason = models.CharField(
        _("Причина последнего разлогина"),
        max_length=64,
        blank=True,
        help_text=_("Что сообщило приложение: login_redirect, no_cookies, banned…"),
    )
    created_at = models.DateTimeField(_("Создан"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Обновлён"), auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("Аккаунт Pinduoduo")
        verbose_name_plural = _("Аккаунты Pinduoduo")

    def __str__(self):
        return f"{self.user.phone} Pinduoduo"

    def session_lifetime(self):
        """Сколько прожила последняя сессия. None — если ещё жива или не было."""
        if not self.session_started_at or not self.session_expired_at:
            return None
        if self.session_expired_at < self.session_started_at:
            return None  # разлогин от прошлой сессии, уже перелогинились
        return self.session_expired_at - self.session_started_at
