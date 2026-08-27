"""Каскад каналов доставки OTP: WhatsApp первым, SMS запасным.

Каскад — единственное место, где сбой канала не должен доходить до клиента.
Если перебор сломается, вход не упадёт заметно: код просто перестанет
доходить части людей, а в API по-прежнему будет 200.
"""

import pytest
from django.test import override_settings

from tests.factories import CargoCompanyFactory
from users.models import SMSCode
from users.services import send_sms_code
from users.sms.exceptions import SmsBackendError
from users.sms.whatsapp import WahaWhatsAppBackend, normalize_phone_for_whatsapp


class OkBackend:
    def __init__(self, provider):
        self.provider = provider
        self.calls = []

    def send_otp(self, phone, code, purpose, message_id):
        self.calls.append(phone)
        return {"message_id": message_id, "provider": self.provider}


class FailingBackend:
    def __init__(self):
        self.calls = []

    def send_otp(self, phone, code, purpose, message_id):
        self.calls.append(phone)
        raise SmsBackendError("канал недоступен", status_code=500)


@pytest.mark.django_db
def test_whatsapp_first_stops_cascade(monkeypatch):
    """SMS не должна уходить, если WhatsApp уже доставил — иначе платим дважды."""
    whatsapp, sms = OkBackend("whatsapp"), OkBackend("nikita")
    monkeypatch.setattr(
        "users.services.get_otp_backends",
        lambda: [("whatsapp", whatsapp), ("sms", sms)],
    )

    code = send_sms_code("+996700111111", cargo=CargoCompanyFactory())

    assert code.channel == "whatsapp"
    assert whatsapp.calls and not sms.calls


@pytest.mark.django_db
def test_falls_back_to_sms_when_whatsapp_fails(monkeypatch):
    """У номера может не быть WhatsApp — человек всё равно обязан получить код."""
    whatsapp, sms = FailingBackend(), OkBackend("nikita")
    monkeypatch.setattr(
        "users.services.get_otp_backends",
        lambda: [("whatsapp", whatsapp), ("sms", sms)],
    )

    code = send_sms_code("+996700222222", cargo=CargoCompanyFactory())

    assert code.channel == "sms"
    assert whatsapp.calls and sms.calls


@pytest.mark.django_db
@override_settings(OTP_MASTER_CODE="")
def test_all_channels_failed_raises(monkeypatch):
    from rest_framework.exceptions import ValidationError

    monkeypatch.setattr(
        "users.services.get_otp_backends",
        lambda: [("whatsapp", FailingBackend()), ("sms", FailingBackend())],
    )

    with pytest.raises(ValidationError):
        send_sms_code("+996700333333", cargo=CargoCompanyFactory())
    assert not SMSCode.objects.filter(phone="+996700333333").exists()


@pytest.mark.django_db
@override_settings(OTP_MASTER_CODE="9999")
def test_master_code_still_works_when_all_channels_fail(monkeypatch):
    """Мастер-код был запасным выходом при сбое SMS — каскад не должен его убрать."""
    monkeypatch.setattr(
        "users.services.get_otp_backends",
        lambda: [("whatsapp", FailingBackend()), ("sms", FailingBackend())],
    )

    code = send_sms_code("+996700555555", cargo=CargoCompanyFactory())

    assert code is not None
    assert code.channel == ""  # доставки не было


# --- Разбор настройки каналов ---


@override_settings(OTP_CHANNELS="sms")
def test_default_is_sms_only():
    from users.sms.factory import get_otp_backends

    assert [name for name, _ in get_otp_backends()] == ["sms"]


@override_settings(OTP_CHANNELS="whatsapp,sms", WHATSAPP_API_URL="http://127.0.0.1:3000")
def test_channels_keep_declared_order():
    from users.sms.factory import get_otp_backends

    assert [name for name, _ in get_otp_backends()] == ["whatsapp", "sms"]


@override_settings(OTP_CHANNELS="whatsapp, , telegram ,sms")
def test_unknown_and_empty_channels_ignored():
    from users.sms.factory import get_otp_backends

    assert [name for name, _ in get_otp_backends()] == ["whatsapp", "sms"]


@override_settings(OTP_CHANNELS="")
def test_broken_setting_falls_back_to_sms():
    """Пустой OTP_CHANNELS не должен оставить вход вообще без канала."""
    from users.sms.factory import get_otp_backends

    assert [name for name, _ in get_otp_backends()] == ["sms"]


# --- WhatsApp-бэкенд ---


def test_phone_normalized_to_digits():
    assert normalize_phone_for_whatsapp("+996 700-11-22-33") == "996700112233"


@override_settings(WHATSAPP_API_URL="")
def test_whatsapp_without_url_raises():
    with pytest.raises(SmsBackendError):
        WahaWhatsAppBackend(base_url="").send_otp("+996700000000", "1234", "login", "M1")
