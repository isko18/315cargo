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
        PARCEL_SCANNED = "parcel_scanned", _("Сканирование посылки")
        PARCEL_STATUS_CHANGED = "parcel_status_changed", _("Смена статуса посылки")
        PARCEL_ISSUED = "parcel_issued", _("Выдача посылки")
        CITY_DELIVERY_CREATED = "city_delivery_created", _("Создана доставка по городу")
        CITY_DELIVERY_DELIVERED = "city_delivery_delivered", _("Завершена доставка по городу")
        PINDUODUO_CONNECTED = "pinduoduo_connected", _("Подключение Pinduoduo")
        PINDUODUO_DISCONNECTED = "pinduoduo_disconnected", _("Отключение Pinduoduo")
        PINDUODUO_SYNCED = "pinduoduo_synced", _("Синхронизация Pinduoduo")
        PINDUODUO_SESSION_EXPIRED = (
            "pinduoduo_session_expired",
            _("Сессия Pinduoduo истекла"),
        )
        TAOBAO_CONNECTED = "taobao_connected", _("Подключение Taobao")
        TAOBAO_DISCONNECTED = "taobao_disconnected", _("Отключение Taobao")
        TAOBAO_SYNCED = "taobao_synced", _("Синхронизация Taobao")
        TAOBAO_SESSION_EXPIRED = "taobao_session_expired", _("Сессия Taobao истекла")
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


class DeliveryAddress(models.Model):
    """Глобальный адрес доставки (склад в Китае для PDD).

    Единственная запись на всю платформу (singleton, pk=1). Заполняет только
    супер-владелец; все карго и их клиенты используют этот же адрес. Клиент в
    приложении получает адрес с уже вшитым СВОИМ клиентским кодом — он стоит в
    конце адреса, перед индексом, чтобы при приёмке в Китае опознать коробку.
    """

    recipient_name = models.CharField(
        _("ФИО получателя по умолчанию (收货人)"),
        max_length=128,
        blank=True,
        help_text=_(
            "Запасное имя получателя. Основное задаётся у каждого карго отдельно "
            "— у них разные люди на приёмке в Китае."
        ),
    )
    phone = models.CharField(_("Телефон (手机号)"), max_length=32, blank=True)
    province = models.CharField(_("Провинция (省)"), max_length=64, blank=True)
    city = models.CharField(_("Город (市)"), max_length=64, blank=True)
    district = models.CharField(_("Район (区/县)"), max_length=64, blank=True)
    detail_address = models.CharField(_("Детальный адрес (详细地址)"), max_length=255, blank=True)
    # Не используется: индекс убран из адреса — маркетплейс подставляет его сам
    # по 省市区, а лишнее число в конце мешало распознаванию. Колонку оставили,
    # чтобы не терять заполненные значения.
    postal_code = models.CharField(_("Индекс (邮编), не используется"), max_length=16, blank=True)
    instructions = models.TextField(
        _("Памятка клиенту"),
        blank=True,
        help_text=_("Напр.: обязательно укажите свой код в имени получателя."),
    )
    is_active = models.BooleanField(_("Активен"), default=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Кто изменил"),
    )
    updated_at = models.DateTimeField(_("Обновлён"), auto_now=True)

    class Meta:
        verbose_name = _("Адрес доставки (Китай)")
        verbose_name_plural = _("Адрес доставки (Китай)")

    def save(self, *args, **kwargs):
        # Singleton: всегда одна запись.
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return _("Адрес доставки (Китай)")

    def recipient_for(self, client_code=None, cargo_recipient=None):
        """Имя получателя (收货人) на складе.

        У каждого карго свой человек на приёмке, поэтому приоритет — ФИО из
        карго клиента; поле здесь остаётся общим запасным. Если не задано ни
        то, ни другое, подставляем код клиента: коробку всё равно нужно уметь
        опознать.
        """
        return (
            (cargo_recipient or "").strip()
            or (self.recipient_name or "").strip()
            or (client_code or "").strip()
        )

    def region_line(self):
        """省市区 одной строкой (как ожидает умное распознавание PDD)."""
        return "".join(p for p in (self.province, self.city, self.district) if p)

    def detail_for(self, address_suffix=None):
        """Детальный адрес с припиской карго: «…仓315库» + «东» → «…仓315库东».

        Приписка клеится слитно — это часть номера склада, а не отдельное слово.
        """
        return (self.detail_address or "").strip() + (address_suffix or "").strip()

    def one_line(
        self,
        client_code=None,
        cargo_code=None,
        cargo_recipient=None,
        address_suffix=None,
    ):
        """Готовая строка для вставки в PDD (智能填写).

        Порядок: ФИО, телефон, 省市区, детальный адрес (с припиской карго),
        код карго, код клиента. ФИО, код и приписка берутся из карго клиента.

        Индекс в строку не входит: маркетплейсы подставляют его сами по 省市区,
        а лишнее число в конце сбивало распознавание адреса.
        """
        recipient = self.recipient_for(client_code, cargo_recipient)
        code = (client_code or "").strip()
        parts = [
            recipient,
            (self.phone or "").strip(),
            self.region_line(),
            self.detail_for(address_suffix),
            (cargo_code or "").strip(),
            "" if code == recipient else code,  # без дубля, если ФИО не задано
        ]
        return " ".join(p for p in parts if p)
