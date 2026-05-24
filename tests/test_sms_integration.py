import pytest
from django.test import override_settings
from rest_framework.exceptions import ValidationError

from tests.factories import CargoCompanyFactory
from users.models import SMSCode
from users.services import send_sms_code
from users.sms.exceptions import SmsBackendError


@pytest.mark.django_db
@override_settings(SMS_BACKEND="mock")
def test_send_sms_code_uses_mock_backend(api_client):
    cargo = CargoCompanyFactory()
    response = api_client.post(
        "/api/auth/send-code/",
        {"phone": "+996700444444", "cargo_id": cargo.id, "purpose": "register"},
        format="json",
    )
    assert response.status_code == 200
    sms = SMSCode.objects.get(phone="+996700444444")
    assert len(sms.code) == 4
    assert sms.provider_message_id


@pytest.mark.django_db
@override_settings(
    SMS_BACKEND="nikita",
    NIKITA_SMS_LOGIN="login",
    NIKITA_SMS_PASSWORD="pwd",
)
def test_send_sms_code_nikita_failure_deletes_nothing(monkeypatch, api_client):
    def fail(*args, **kwargs):
        raise SmsBackendError("Недостаточно средств", status_code=4)

    monkeypatch.setattr("users.services.get_sms_backend", lambda: type("B", (), {"send_otp": fail})())

    with pytest.raises(ValidationError):
        send_sms_code("+996700555555")

    assert not SMSCode.objects.filter(phone="+996700555555").exists()


@pytest.mark.django_db
@override_settings(
    SMS_BACKEND="nikita",
    NIKITA_SMS_LOGIN="login",
    NIKITA_SMS_PASSWORD="pwd",
)
def test_send_sms_code_nikita_success(monkeypatch):
    class FakeBackend:
        def send_otp(self, phone, code, purpose, message_id):
            return {"message_id": message_id, "provider": "nikita"}

    monkeypatch.setattr("users.services.get_sms_backend", lambda: FakeBackend())
    sms = send_sms_code("+996700666666")
    assert sms.provider_message_id
    assert sms.code
