from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

User = get_user_model()


def resolve_staff_user_by_phone(phone):
    phone = (phone or "").strip()
    if not phone:
        return None

    candidates = User.objects.filter(
        phone=phone,
        is_active=True,
    ).filter(
        models.Q(is_staff=True) | models.Q(is_superuser=True)
    )

    count = candidates.count()
    if count == 0:
        return None
    if count == 1:
        return candidates.get()

    superusers = candidates.filter(is_superuser=True, cargo__isnull=True)
    if superusers.count() == 1:
        return superusers.get()

    raise ValidationError(
        _("Несколько учётных записей с этим номером. Обратитесь к администратору."),
        code="ambiguous_phone",
    )


class AdminPhoneAuthenticationForm(AdminAuthenticationForm):
    username = forms.CharField(
        label=_("Телефон"),
        max_length=32,
        widget=forms.TextInput(
            attrs={
                "autofocus": True,
                "autocapitalize": "none",
                "autocomplete": "username",
            }
        ),
    )

    error_messages = {
        **AdminAuthenticationForm.error_messages,
        "invalid_login": _(
            "Неверный телефон или пароль. Проверьте данные и попробуйте снова."
        ),
    }

    def clean(self):
        phone = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if phone is not None and password:
            try:
                user = resolve_staff_user_by_phone(phone)
            except ValidationError:
                raise

            if user is None:
                raise self.get_invalid_login_error()

            self.user_cache = authenticate(
                self.request,
                username=user.login_key,
                password=password,
            )

            if self.user_cache is None:
                raise self.get_invalid_login_error()

            self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data
