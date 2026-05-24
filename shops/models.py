from django.db import models
from django.utils.translation import gettext_lazy as _


class Shop(models.Model):
    class OpenType(models.TextChoices):
        WEBVIEW = "webview", _("WebView в приложении")
        EXTERNAL_APP = "external_app", _("Внешнее приложение")
        BROWSER = "browser", _("Внешний браузер")

    class ClientCodeStrategy(models.TextChoices):
        QUERY_PARAM = "query_param", _("Подставить в URL")
        CLIPBOARD = "clipboard", _("Скопировать в буфер обмена")
        MANUAL_INSTRUCTION = "manual_instruction", _("Показать инструкцию")

    cargo = models.ForeignKey(
        "cargo.CargoCompany",
        on_delete=models.CASCADE,
        related_name="shops",
        verbose_name=_("Карго-центр"),
    )
    title = models.CharField(_("Название"), max_length=255)
    slug = models.SlugField(_("Идентификатор"))
    icon = models.ImageField(_("Иконка"), upload_to="shop_icons/", null=True, blank=True)
    url = models.URLField(_("Ссылка"))
    open_type = models.CharField(
        _("Способ открытия"),
        max_length=32,
        choices=OpenType.choices,
        default=OpenType.WEBVIEW,
    )
    client_code_strategy = models.CharField(
        _("Стратегия передачи клиентского кода"),
        max_length=32,
        choices=ClientCodeStrategy.choices,
        default=ClientCodeStrategy.QUERY_PARAM,
    )
    query_param_name = models.CharField(_("Параметр в URL"), max_length=64, blank=True)
    sort_order = models.PositiveIntegerField(_("Порядок"), default=0)
    is_active = models.BooleanField(_("Активен"), default=True)
    created_at = models.DateTimeField(_("Создан"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Обновлён"), auto_now=True)

    class Meta:
        ordering = ("sort_order", "title")
        verbose_name = _("Магазин")
        verbose_name_plural = _("Магазины")
        constraints = [
            models.UniqueConstraint(
                fields=("cargo", "slug"),
                name="unique_shop_slug_per_cargo",
            ),
        ]

    def __str__(self):
        return self.title
