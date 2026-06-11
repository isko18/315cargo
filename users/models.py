from datetime import timedelta

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .constants import OTP_CODE_LENGTH


class UserManager(BaseUserManager):
    def create_user(self, phone, password=None, **extra_fields):
        if not phone:
            raise ValueError("Phone is required")
        cargo = extra_fields.get("cargo")
        if not cargo and not extra_fields.get("is_superuser"):
            raise ValueError("Cargo is required for client users")
        user = self.model(phone=phone, **extra_fields)
        user.login_key = user.build_login_key()
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        return self.create_user(phone, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    cargo = models.ForeignKey(
        "cargo.CargoCompany",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
        verbose_name=_("Карго-центр"),
    )
    phone = models.CharField(_("Телефон"), max_length=32)
    login_key = models.CharField(_("Ключ входа"), max_length=64, unique=True, editable=False)
    full_name = models.CharField(_("ФИО"), max_length=255, blank=True)
    pickup_point = models.ForeignKey(
        "pickup_points.PickupPoint",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
        verbose_name=_("ПВЗ"),
    )
    client_code = models.CharField(
        _("Клиентский код"), max_length=16, null=True, blank=True
    )
    qr_code_image = models.ImageField(
        _("QR-код"), upload_to="qr_codes/", null=True, blank=True
    )
    is_active = models.BooleanField(_("Активен"), default=True)
    is_staff = models.BooleanField(_("Сотрудник"), default=False)
    is_cargo_admin = models.BooleanField(
        _("Администратор карго"),
        default=False,
        help_text=_("Полный доступ к управлению своим карго-центром в админке и API"),
    )
    created_at = models.DateTimeField(_("Создан"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Обновлён"), auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "login_key"
    REQUIRED_FIELDS = ["phone"]

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("Клиент")
        verbose_name_plural = _("Клиенты")
        constraints = [
            models.UniqueConstraint(
                fields=("cargo", "phone"),
                name="unique_user_phone_per_cargo",
            ),
            models.UniqueConstraint(
                fields=("cargo", "client_code"),
                name="unique_user_client_code_per_cargo",
                condition=models.Q(client_code__isnull=False),
            ),
        ]

    def __str__(self):
        return self.phone

    def build_login_key(self):
        if self.is_superuser and not self.cargo_id:
            return f"su:{self.phone}"
        if not self.cargo_id:
            raise ValueError("cargo is required to build login_key")
        return f"{self.cargo_id}:{self.phone}"

    def save(self, *args, **kwargs):
        if self.is_cargo_admin and not self.is_superuser:
            self.is_staff = True
            if not self.cargo_id:
                raise ValueError("cargo is required for cargo administrators")
        if self.phone and (self.cargo_id or self.is_superuser):
            self.login_key = self.build_login_key()
        super().save(*args, **kwargs)
        self._sync_cargo_admin_group()

    def _sync_cargo_admin_group(self):
        from django.contrib.auth.models import Group

        group = Group.objects.filter(name="Администратор карго").first()
        if not group:
            return
        if self.is_cargo_admin and not self.is_superuser:
            self.groups.add(group)
        else:
            self.groups.remove(group)


class SMSCode(models.Model):
    class Purpose(models.TextChoices):
        REGISTER = "register", _("Регистрация")
        LOGIN = "login", _("Вход")

    cargo = models.ForeignKey(
        "cargo.CargoCompany",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sms_codes",
        verbose_name=_("Карго-центр"),
    )
    phone = models.CharField(_("Телефон"), max_length=32, db_index=True)
    code = models.CharField(_("Код"), max_length=OTP_CODE_LENGTH)
    purpose = models.CharField(_("Назначение"), max_length=16, choices=Purpose.choices)
    is_used = models.BooleanField(_("Использован"), default=False)
    attempts = models.PositiveSmallIntegerField(_("Попыток ввода"), default=0)
    expires_at = models.DateTimeField(_("Истекает"))
    provider_message_id = models.CharField(
        _("ID сообщения у провайдера"),
        max_length=12,
        blank=True,
        db_index=True,
    )
    created_at = models.DateTimeField(_("Создан"), auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("SMS-код")
        verbose_name_plural = _("SMS-коды")

    @property
    def is_expired(self):
        return self.expires_at <= timezone.now()

    @classmethod
    def default_expires_at(cls):
        return timezone.now() + timedelta(minutes=5)

    def __str__(self):
        return f"{self.phone} {self.purpose}"
