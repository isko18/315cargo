from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class NotificationType(models.TextChoices):
    AUTH = "auth", _("Авторизация")
    ORDER_CREATED = "order_created", _("Новый заказ")
    ORDER_STATUS_CHANGED = "order_status_changed", _("Изменение статуса заказа")
    PARCEL_STATUS_CHANGED = "parcel_status_changed", _("Изменение статуса посылки")
    PARCEL_AT_PICKUP_POINT = "parcel_at_pickup_point", _("Посылка в ПВЗ")
    CITY_DELIVERY_CREATED = "city_delivery_created", _("Создана доставка по городу")
    CITY_DELIVERY_STATUS_CHANGED = "city_delivery_status_changed", _("Изменение статуса доставки")
    PINDUODUO_CONNECTED = "pinduoduo_connected", _("Pinduoduo подключён")
    PINDUODUO_SYNCED = "pinduoduo_synced", _("Pinduoduo синхронизирован")
    MARKETING = "marketing", _("Рекламное")
    SYSTEM = "system", _("Системное")


class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name=_("Клиент"),
    )
    title = models.CharField(_("Заголовок"), max_length=255)
    body = models.TextField(_("Текст"))
    type = models.CharField(
        _("Тип"),
        max_length=64,
        choices=NotificationType.choices,
        default=NotificationType.SYSTEM,
    )
    is_read = models.BooleanField(_("Прочитано"), default=False)
    data = models.JSONField(_("Доп. данные"), default=dict, blank=True)
    created_at = models.DateTimeField(_("Создано"), auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("Уведомление")
        verbose_name_plural = _("Уведомления")

    def __str__(self):
        return self.title


class DeviceToken(models.Model):
    class Platform(models.TextChoices):
        IOS = "ios", "iOS"
        ANDROID = "android", "Android"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="device_tokens",
        verbose_name=_("Клиент"),
    )
    token = models.CharField(_("FCM-токен"), max_length=512, unique=True)
    platform = models.CharField(_("Платформа"), max_length=16, choices=Platform.choices)
    is_active = models.BooleanField(_("Активен"), default=True)
    created_at = models.DateTimeField(_("Создан"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Обновлён"), auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("Токен устройства")
        verbose_name_plural = _("Токены устройств")

    def __str__(self):
        return f"{self.user.phone} {self.platform}"


class NotificationPreference(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preference",
        verbose_name=_("Клиент"),
    )
    push_enabled = models.BooleanField(_("Push-уведомления"), default=True)
    parcel_status_enabled = models.BooleanField(_("Статусы посылок"), default=True)
    order_status_enabled = models.BooleanField(_("Статусы заказов"), default=True)
    city_delivery_enabled = models.BooleanField(_("Доставка по городу"), default=True)
    marketing_enabled = models.BooleanField(_("Рекламные уведомления"), default=False)
    created_at = models.DateTimeField(_("Создано"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Обновлено"), auto_now=True)

    class Meta:
        verbose_name = _("Настройки уведомлений")
        verbose_name_plural = _("Настройки уведомлений")

    def __str__(self):
        return f"{self.user.phone} preferences"

    def allows(self, notification_type):
        mapping = {
            NotificationType.PARCEL_STATUS_CHANGED: self.parcel_status_enabled,
            NotificationType.PARCEL_AT_PICKUP_POINT: self.parcel_status_enabled,
            NotificationType.ORDER_CREATED: self.order_status_enabled,
            NotificationType.ORDER_STATUS_CHANGED: self.order_status_enabled,
            NotificationType.CITY_DELIVERY_CREATED: self.city_delivery_enabled,
            NotificationType.CITY_DELIVERY_STATUS_CHANGED: self.city_delivery_enabled,
            NotificationType.MARKETING: self.marketing_enabled,
        }
        return mapping.get(notification_type, True)
