from django.db import models
from django.utils.translation import gettext_lazy as _

# Клиентский код = префикс карго + порядковый номер фиксированной ширины
# (X0001, X0002, …). Ширина одна на всю платформу — меняется только префикс.
CLIENT_CODE_DIGITS = 4
DEFAULT_CLIENT_CODE_PREFIX = "C"


class CargoCompany(models.Model):
    title = models.CharField(_("Название"), max_length=255)
    slug = models.SlugField(_("Идентификатор"), unique=True)
    code = models.CharField(
        _("Код карго"),
        max_length=32,
        null=True,
        blank=True,
        unique=True,
        help_text=_(
            "Код склада в Китае (напр. x69610). Клиенты этого карго указывают его "
            "в адресе доставки перед своим кодом."
        ),
    )
    description = models.TextField(_("Описание"), blank=True)
    logo = models.ImageField(_("Логотип"), upload_to="cargo_logos/", null=True, blank=True)
    phone = models.CharField(_("Телефон"), max_length=32, blank=True)
    address = models.TextField(_("Адрес"), blank=True)
    price_per_kg_kgs = models.DecimalField(
        _("Цена за кг, сом"),
        max_digits=8,
        decimal_places=2,
        default=0,
        help_text=_("Стоимость доставки за 1 кг в сомах (KGS)"),
    )
    client_code_prefix = models.CharField(
        _("Префикс кода клиента"),
        max_length=6,
        default=DEFAULT_CLIENT_CODE_PREFIX,
        unique=True,
        help_text=_(
            "Буквы перед номером клиента: «X» → X0001, X0002… Уникален на карго: "
            "по коду клиента коробку опознают в Китае, где посылки всех карго "
            "лежат вместе. Менять можно в любой момент — уже выданные коды не "
            "пересчитываются."
        ),
    )
    client_code_seq = models.PositiveIntegerField(
        _("Счётчик кодов клиентов"),
        default=0,
        help_text=_("Номер последнего выданного клиентского кода этого карго."),
    )
    is_active = models.BooleanField(_("Активен"), default=True)
    created_at = models.DateTimeField(_("Создан"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Обновлён"), auto_now=True)

    class Meta:
        ordering = ("title",)
        verbose_name = _("Карго-центр")
        verbose_name_plural = _("Карго-центры")

    def save(self, *args, **kwargs):
        # Пустой код храним как NULL: unique=True иначе запретит второе «''».
        self.code = (self.code or "").strip() or None
        # Счётчик кодов двигает только выдача кода (там update_fields). Полное
        # сохранение объекта, прочитанного до выдачи, не должно откатывать
        # счётчик назад — иначе следующий клиент получит уже занятый номер.
        update_fields = kwargs.get("update_fields")
        if self.pk and (update_fields is None or "client_code_seq" not in update_fields):
            current = (
                CargoCompany.objects.filter(pk=self.pk)
                .values_list("client_code_seq", flat=True)
                .first()
            )
            if current is not None:
                self.client_code_seq = current
        super().save(*args, **kwargs)

    def format_client_code(self, number):
        """Номер → клиентский код в формате этого карго (5 → «X0005»)."""
        prefix = (self.client_code_prefix or DEFAULT_CLIENT_CODE_PREFIX).strip()
        return f"{prefix}{number:0{CLIENT_CODE_DIGITS}d}"

    def next_client_code(self):
        """Какой код получит следующий клиент — для предпросмотра в панели."""
        return self.format_client_code(self.client_code_seq + 1)

    def __str__(self):
        return self.title
