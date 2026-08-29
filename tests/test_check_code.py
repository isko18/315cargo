"""Отдельная проверка OTP до завершения регистрации.

Регистрация идёт в два экрана: сначала код, потом ФИО и ПВЗ. verify-code на
первом экране не годится — он гасит код ещё до того, как вьюха убедится, что
анкета заполнена. Клиент получал бы ошибку с уже потраченным кодом и ждал
минуту нового.
"""

import pytest
from django.test import override_settings
from django.utils import timezone

from tests.factories import CargoCompanyFactory, UserFactory
from users.constants import MAX_OTP_ATTEMPTS
from users.models import SMSCode

URL = "/api/auth/check-code/"


def make_code(cargo, phone="+996700123123", code="1234"):
    return SMSCode.objects.create(
        phone=phone,
        cargo=cargo,
        code=code,
        purpose=SMSCode.Purpose.LOGIN,
        expires_at=SMSCode.default_expires_at(),
    )


@pytest.mark.django_db
def test_correct_code_is_not_burned(api_client):
    """Главное: после проверки код обязан остаться годным для verify-code."""
    cargo = CargoCompanyFactory()
    sms = make_code(cargo)

    response = api_client.post(
        URL, {"phone": sms.phone, "code": "1234", "cargo_id": cargo.id}, format="json"
    )

    assert response.status_code == 200
    assert response.data["valid"] is True
    sms.refresh_from_db()
    assert sms.is_used is False


@pytest.mark.django_db
def test_check_then_verify_completes_registration(api_client):
    """Полный сценарий: проверили код, собрали анкету, завершили регистрацию."""
    cargo = CargoCompanyFactory()
    sms = make_code(cargo)
    from tests.factories import PickupPointFactory

    pickup = PickupPointFactory(cargo=cargo)

    assert api_client.post(
        URL, {"phone": sms.phone, "code": "1234", "cargo_id": cargo.id}, format="json"
    ).status_code == 200

    response = api_client.post(
        "/api/auth/verify-code/",
        {
            "phone": sms.phone,
            "code": "1234",
            "cargo_id": cargo.id,
            "pickup_point_id": pickup.id,
            "full_name": "Иван Иванов",
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.data["access"]


@pytest.mark.django_db
def test_wrong_code_counts_attempt(api_client):
    """Без счёта попыток проверка без сжигания стала бы бесплатным перебором."""
    cargo = CargoCompanyFactory()
    sms = make_code(cargo)

    response = api_client.post(
        URL, {"phone": sms.phone, "code": "9999", "cargo_id": cargo.id}, format="json"
    )

    assert response.status_code == 400
    sms.refresh_from_db()
    assert sms.attempts == 1


@pytest.mark.django_db
def test_attempts_exhausted_burns_code(api_client):
    cargo = CargoCompanyFactory()
    sms = make_code(cargo)

    for _ in range(MAX_OTP_ATTEMPTS):
        api_client.post(
            URL, {"phone": sms.phone, "code": "9999", "cargo_id": cargo.id}, format="json"
        )

    sms.refresh_from_db()
    assert sms.is_used is True


@pytest.mark.django_db
def test_expired_code_rejected(api_client):
    cargo = CargoCompanyFactory()
    sms = make_code(cargo)
    sms.expires_at = timezone.now() - timezone.timedelta(minutes=1)
    sms.save(update_fields=("expires_at",))

    response = api_client.post(
        URL, {"phone": sms.phone, "code": "1234", "cargo_id": cargo.id}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_code_from_other_cargo_rejected(api_client):
    """Код, выданный для другого карго, не должен подходить."""
    cargo_a, cargo_b = CargoCompanyFactory(), CargoCompanyFactory()
    sms = make_code(cargo_a)

    response = api_client.post(
        URL, {"phone": sms.phone, "code": "1234", "cargo_id": cargo_b.id}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_reports_new_user(api_client):
    """Приложению нужно знать заранее, показывать анкету или сразу вход."""
    cargo = CargoCompanyFactory()
    sms = make_code(cargo)

    data = api_client.post(
        URL, {"phone": sms.phone, "code": "1234", "cargo_id": cargo.id}, format="json"
    ).data
    assert data["is_new_user"] is True


@pytest.mark.django_db
def test_reports_existing_user(api_client, pickup_point):
    cargo = pickup_point.cargo
    UserFactory(phone="+996700555001", cargo=cargo, pickup_point=pickup_point)
    sms = make_code(cargo, phone="+996700555001")

    data = api_client.post(
        URL, {"phone": sms.phone, "code": "1234", "cargo_id": cargo.id}, format="json"
    ).data
    assert data["is_new_user"] is False


@pytest.mark.django_db
@override_settings(OTP_MASTER_CODE="7777")
def test_master_code_accepted(api_client):
    cargo = CargoCompanyFactory()
    response = api_client.post(
        URL, {"phone": "+996700123123", "code": "7777", "cargo_id": cargo.id}, format="json"
    )
    assert response.status_code == 200
