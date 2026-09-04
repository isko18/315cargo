from django.db import models
from django.utils.translation import gettext_lazy as _


class PickupPoint(models.Model):
    cargo = models.ForeignKey(
        "cargo.CargoCompany",
        on_delete=models.CASCADE,
        related_name="pickup_points",
        verbose_name=_("Карго-центр"),
    )
    title = models.CharField(_("Название"), max_length=255)
    address = models.TextField(_("Адрес"))
    phone = models.CharField(_("Контактный телефон"), max_length=32, blank=True)
    work_schedule = models.CharField(_("График работы"), max_length=255, blank=True)
    client_code_prefix = models.CharField(
        _("Префикс кода клиента"),
        max_length=10,
        blank=True,
        help_text=_(
            "Свой префикс этого ПВЗ: «ISIM» → ISIM0001. Пусто — берётся префикс "
            "карго, и код будет общим на все ПВЗ. Уникален среди всех карго и "
            "ПВЗ: по коду клиента коробку опознают в Китае, где посылки лежат "
            "вместе. Менять можно в любой момент — выданные коды не "
            "пересчитываются."
        ),
    )
    client_code_seq = models.PositiveIntegerField(
        _("Счётчик кодов клиентов"),
        default=0,
        help_text=_(
            "Номер последнего кода, выданного этим ПВЗ. Своя нумерация "
            "включается вместе с префиксом."
        ),
    )
    is_active = models.BooleanField(_("Активен"), default=True)
    created_at = models.DateTimeField(_("Создан"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Обновлён"), auto_now=True)

    class Meta:
        ordering = ("title",)
        verbose_name = _("ПВЗ")
        verbose_name_plural = _("ПВЗ")

    def save(self, *args, **kwargs):
        # Счётчик двигает только выдача кода (там update_fields). Полное
        # сохранение объекта, прочитанного до выдачи, не должно откатывать его
        # назад — иначе следующий клиент получит уже занятый номер.
        update_fields = kwargs.get("update_fields")
        if self.pk and (update_fields is None or "client_code_seq" not in update_fields):
            current = (
                PickupPoint.objects.filter(pk=self.pk)
                .values_list("client_code_seq", flat=True)
                .first()
            )
            if current is not None:
                self.client_code_seq = current
        super().save(*args, **kwargs)

    @property
    def has_own_client_codes(self):
        """Своя нумерация включена, только если задан префикс."""
        return bool((self.client_code_prefix or "").strip())

    def format_client_code(self, number):
        from cargo.models import CLIENT_CODE_DIGITS

        prefix = (self.client_code_prefix or "").strip()
        return f"{prefix}{number:0{CLIENT_CODE_DIGITS}d}"

    def next_client_code(self):
        """Какой код получит следующий клиент этого ПВЗ — для предпросмотра."""
        if not self.has_own_client_codes:
            return self.cargo.next_client_code()
        return self.format_client_code(self.client_code_seq + 1)

    def __str__(self):
        return self.title
