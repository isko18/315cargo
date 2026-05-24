from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class AuditLog(models.Model):
    class Action(models.TextChoices):
        USER_REGISTERED = "user_registered", _("Регистрация клиента")
        USER_LOGIN = "user_login", _("Вход клиента")
        USER_LOGOUT = "user_logout", _("Выход клиента")
        USER_BLOCKED = "user_blocked", _("Блокировка клиента")
        USER_UNBLOCKED = "user_unblocked", _("Разблокировка клиента")
        PARCEL_IMPORTED = "parcel_imported", _("Импорт посылки")
        PARCEL_STATUS_CHANGED = "parcel_status_changed", _("Смена статуса посылки")
        PARCEL_ISSUED = "parcel_issued", _("Выдача посылки")
        CITY_DELIVERY_CREATED = "city_delivery_created", _("Создана доставка по городу")
        CITY_DELIVERY_DELIVERED = "city_delivery_delivered", _("Завершена доставка по городу")
        PINDUODUO_CONNECTED = "pinduoduo_connected", _("Подключение Pinduoduo")
        PINDUODUO_DISCONNECTED = "pinduoduo_disconnected", _("Отключение Pinduoduo")
        PINDUODUO_SYNCED = "pinduoduo_synced", _("Синхронизация Pinduoduo")
        ADMIN_ACTION = "admin_action", _("Действие администратора")

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs_initiated",
        verbose_name=_("Кто выполнил"),
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs_targeted",
        verbose_name=_("Кого касается"),
    )
    action = models.CharField(_("Действие"), max_length=64, choices=Action.choices)
    description = models.TextField(_("Описание"), blank=True)
    metadata = models.JSONField(_("Доп. данные"), default=dict, blank=True)
    ip_address = models.GenericIPAddressField(_("IP"), null=True, blank=True)
    user_agent = models.CharField(_("User-Agent"), max_length=512, blank=True)
    created_at = models.DateTimeField(_("Создан"), auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("Запись аудита")
        verbose_name_plural = _("Журнал аудита")
        indexes = [
            models.Index(fields=("action", "created_at")),
            models.Index(fields=("target_user", "created_at")),
        ]

    def __str__(self):
        return f"{self.action} {self.created_at:%Y-%m-%d %H:%M}"
