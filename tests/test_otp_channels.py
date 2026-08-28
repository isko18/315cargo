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


@override_settings(WHATSAPP_BRAND="315CARGO", NIKITA_SMS_BRAND="SMSPRO.KG")
def test_whatsapp_text_uses_own_brand_not_sms_sender():
    """В NIKITA_SMS_BRAND лежит идентификатор отправителя оператора связи.
    В WhatsApp он читается как чужая рассылка, поэтому бренд отдельный."""
    from users.sms.whatsapp import build_otp_text

    text = build_otp_text("1234")
    assert "*315CARGO*" in text
    assert "SMSPRO" not in text


@override_settings(WHATSAPP_BRAND="315CARGO")
def test_whatsapp_text_marks_brand_and_code_bold():
    from users.sms.whatsapp import build_otp_text

    text = build_otp_text("1234")
    assert text.startswith("*315CARGO*")
    assert "*1234*" in text


def test_sms_text_has_no_whatsapp_markup():
    """В SMS разметки быть не должно — звёздочки придут клиенту как есть."""
    from users.sms.nikita import build_otp_text

    assert "*" not in build_otp_text("1234")


def test_otp_lifetime_in_text_matches_real_expiry():
    """Срок в сообщении и реальный TTL — из одной константы, иначе разъедутся."""
    from django.utils import timezone

    from users.constants import OTP_TTL_MINUTES
    from users.models import SMSCode
    from users.sms.whatsapp import build_otp_text

    assert f"{OTP_TTL_MINUTES} мин" in build_otp_text("1234")
    left = (SMSCode.default_expires_at() - timezone.now()).total_seconds() / 60
    assert abs(left - OTP_TTL_MINUTES) < 0.5


@pytest.mark.django_db
def test_provider_message_id_fits_external_ids():
    """Свой message_id был 12 символов, и поле сделали ровно под него.

    WhatsApp возвращает свой id (3EB0274875286487CCC0AD, 22 символа) — на
    Postgres это роняло send-code пятисоткой. В тестах на SQLite длина varchar
    не проверяется вообще, поэтому валидируем через full_clean(): иначе
    регрессия снова уедет на прод незамеченной.
    """
    from django.utils import timezone

    from users.models import SMSCode

    code = SMSCode(
        phone="+996700777777",
        code="1234",
        purpose=SMSCode.Purpose.LOGIN,
        expires_at=SMSCode.default_expires_at(),
        provider_message_id="3EB0274875286487CCC0AD",
        channel="whatsapp",
    )
    code.full_clean(exclude=["cargo"])  # не должно бросить ValidationError
    code.save()
    assert SMSCode.objects.get(pk=code.pk).provider_message_id.endswith("CCC0AD")
    assert timezone.now() < code.expires_at


@pytest.mark.django_db
def test_send_code_response_reports_channel(api_client, monkeypatch):
    """Приложению нужно знать, куда ушёл код, — иначе оно не скажет, где искать."""
    monkeypatch.setattr(
        "users.services.get_otp_backends",
        lambda: [("whatsapp", OkBackend("whatsapp"))],
    )
    cargo = CargoCompanyFactory()

    response = api_client.post(
        "/api/auth/send-code/",
        {"phone": "+996700888888", "cargo_id": cargo.id, "purpose": "register"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["channel"] == "whatsapp"


@pytest.mark.django_db
def test_send_code_channel_empty_for_test_number(api_client, settings):
    """У тестового номера доставки нет — поле должно быть пустым, а не «sms»."""
    settings.OTP_TEST_NUMBERS = {"+996700000000": "0000"}
    cargo = CargoCompanyFactory()

    response = api_client.post(
        "/api/auth/send-code/",
        {"phone": "+996700000000", "cargo_id": cargo.id, "purpose": "register"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["channel"] == ""


# --- Meta Cloud API ---


class FakeMetaResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"messages": [{"id": "wamid.XYZ"}]}
        self.text = text

    def json(self):
        return self._payload


@override_settings(
    META_WA_PHONE_NUMBER_ID="123", META_WA_TOKEN="tok",
    META_WA_TEMPLATE="otp_code", META_WA_LANG="ru", META_WA_API_VERSION="v21.0",
)
def test_meta_payload_repeats_code_in_copy_button(monkeypatch):
    """Код обязан идти и в теле, и в кнопке COPY_CODE.

    Без кнопочного компонента Meta отклоняет отправку — а поймать это можно
    только на живом шаблоне, поэтому проверяем форму запроса здесь.
    """
    from users.sms.meta_whatsapp import MetaWhatsAppBackend

    sent = {}

    def fake_post(url, **kwargs):
        sent["url"] = url
        sent["json"] = kwargs["json"]
        sent["headers"] = kwargs["headers"]
        return FakeMetaResponse()

    monkeypatch.setattr("users.sms.meta_whatsapp.requests.post", fake_post)
    result = MetaWhatsAppBackend().send_otp("+996 700-11-22-33", "1234", "login", "M1")

    body, button = sent["json"]["template"]["components"]
    assert body["parameters"][0]["text"] == "1234"
    assert button["sub_type"] == "COPY_CODE"
    assert button["parameters"][0]["coupon_code"] == "1234"
    # Номер — только цифры, без «+» и разделителей.
    assert sent["json"]["to"] == "996700112233"
    assert sent["headers"]["Authorization"] == "Bearer tok"
    assert "/v21.0/123/messages" in sent["url"]
    assert result["message_id"] == "wamid.XYZ"


@override_settings(META_WA_PHONE_NUMBER_ID="123", META_WA_TOKEN="tok")
def test_meta_error_becomes_backend_error(monkeypatch):
    """Отказ Meta должен уводить каскад в SMS, а не всплывать пятисоткой."""
    from users.sms.meta_whatsapp import MetaWhatsAppBackend

    monkeypatch.setattr(
        "users.sms.meta_whatsapp.requests.post",
        lambda *a, **kw: FakeMetaResponse(status_code=400, text="template not approved"),
    )
    with pytest.raises(SmsBackendError):
        MetaWhatsAppBackend().send_otp("+996700000000", "1234", "login", "M1")


@override_settings(META_WA_PHONE_NUMBER_ID="", META_WA_TOKEN="")
def test_meta_without_credentials_raises():
    from users.sms.meta_whatsapp import MetaWhatsAppBackend

    with pytest.raises(SmsBackendError):
        MetaWhatsAppBackend().send_otp("+996700000000", "1234", "login", "M1")


@override_settings(
    OTP_CHANNELS="whatsapp,sms", WHATSAPP_PROVIDER="meta",
    META_WA_PHONE_NUMBER_ID="123", META_WA_TOKEN="tok",
)
def test_meta_provider_used_under_whatsapp_channel():
    from users.sms.factory import get_otp_backends
    from users.sms.meta_whatsapp import MetaWhatsAppBackend

    backends = get_otp_backends()
    names = [name for name, _ in backends]
    assert names == ["whatsapp", "sms"]
    assert isinstance(dict(backends)["whatsapp"], MetaWhatsAppBackend)
