from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class MarketplaceAccount(models.Model):
    """Подключение клиента к маркетплейсу (Pinduoduo, Taobao, …).

    Сессия живёт в WebView мобильного приложения — сервер её не использует и
    хранит только состояние подключения. Отметки о начале и конце сессии нужны,
    чтобы отличать «клиент открыл официальное приложение» от «куки не пережили
    перезапуск» и от бана: у этих причин разное лечение.
    """

    class Marketplace(models.TextChoices):
        PINDUODUO = "pinduoduo", _("Pinduoduo")
        TAOBAO = "taobao", _("Taobao")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="marketplace_accounts",
        verbose_name=_("Клиент"),
    )
    marketplace = models.CharField(
        _("Маркетплейс"),
        max_length=32,
        choices=Marketplace.choices,
        default=Marketplace.PINDUODUO,
        db_index=True,
    )
    is_connected = models.BooleanField(_("Подключён"), default=False)
    external_user_id = models.CharField(_("ID на стороне маркетплейса"), max_length=128, blank=True)
    session_data = models.JSONField(_("Данные сессии"), default=dict, blank=True)
    last_sync_at = models.DateTimeField(_("Последняя синхронизация"), null=True, blank=True)
    last_sync_error = models.TextField(_("Последняя ошибка"), blank=True)
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
        verbose_name = _("Аккаунт маркетплейса")
        verbose_name_plural = _("Аккаунты маркетплейсов")
        constraints = [
            models.UniqueConstraint(
                fields=("user", "marketplace"),
                name="unique_marketplace_account_per_user",
            ),
        ]

    def __str__(self):
        return f"{self.user.phone} {self.get_marketplace_display()}"

    def session_lifetime(self):
        """Сколько прожила последняя сессия. None — если ещё жива или не было."""
        if not self.session_started_at or not self.session_expired_at:
            return None
        if self.session_expired_at < self.session_started_at:
            return None  # разлогин от прошлой сессии, уже перелогинились
        return self.session_expired_at - self.session_started_at
