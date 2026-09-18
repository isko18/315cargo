"""Песочница для мобильной команды.

Главное здесь — что песочница остаётся песочницей: не показывается клиентам
в приложении и не задевает боевые карго. Второе — идемпотентность: команду
запускают повторно, чтобы сбросить пароль.
"""

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from cargo.models import CargoCompany
from parcels.models import Parcel
from pickup_points.models import PickupPoint

User = get_user_model()

STAFF_PHONE = "+996999000315"


def run(**kwargs):
    out = StringIO()
    call_command("create_test_cargo", stdout=out, **kwargs)
    return out.getvalue()


@pytest.mark.django_db
def test_creates_cargo_points_staff_and_parcels():
    run(password="s3cret-pass")

    cargo = CargoCompany.objects.get(slug="test-cargo")
    assert PickupPoint.objects.filter(cargo=cargo).count() == 2
    assert Parcel.objects.filter(cargo=cargo).count() == 4

    staff = User.objects.get(phone=STAFF_PHONE)
    assert staff.cargo_id == cargo.id
    assert staff.is_staff and staff.is_cargo_admin
    assert staff.check_password("s3cret-pass")


@pytest.mark.django_db
def test_cargo_is_hidden_from_clients():
    """Активное тестовое карго появилось бы в выборе карго в приложении."""
    run(password="x")

    assert not CargoCompany.objects.get(slug="test-cargo").is_active


@pytest.mark.django_db
def test_rerun_resets_password_without_duplicating():
    run(password="first")
    run(password="second")

    assert CargoCompany.objects.filter(slug="test-cargo").count() == 1
    assert User.objects.filter(phone=STAFF_PHONE).count() == 1
    assert PickupPoint.objects.filter(cargo__slug="test-cargo").count() == 2
    assert Parcel.objects.filter(cargo__slug="test-cargo").count() == 4

    staff = User.objects.get(phone=STAFF_PHONE)
    assert staff.check_password("second")


@pytest.mark.django_db
def test_clients_get_codes_of_their_own_pickup():
    """У ПВЗ своя нумерация — по коду должно быть видно, чей клиент."""
    run(password="x")

    codes = sorted(
        User.objects.filter(cargo__slug="test-cargo", is_staff=False).values_list(
            "client_code", flat=True
        )
    )
    assert any(code.startswith("TSTB") for code in codes)
    assert any(code.startswith("TSTO") for code in codes)


@pytest.mark.django_db
def test_staff_can_log_in_with_password(api_client):
    run(password="login-me-1")

    r = api_client.post(
        "/api/auth/token/", {"login": STAFF_PHONE, "password": "login-me-1"}, format="json"
    )

    assert r.status_code == 200
    assert r.data["access"]


@pytest.mark.django_db
def test_dry_run_writes_nothing():
    run(dry_run=True)

    assert not CargoCompany.objects.filter(slug="test-cargo").exists()
    assert not User.objects.filter(phone=STAFF_PHONE).exists()


@pytest.mark.django_db
def test_existing_cargo_is_untouched(cargo):
    """Боевое карго не должно пострадать от запуска команды."""
    before = (cargo.title, cargo.slug, cargo.is_active)

    run(password="x")

    cargo.refresh_from_db()
    assert (cargo.title, cargo.slug, cargo.is_active) == before
    assert not Parcel.objects.filter(cargo=cargo).exists()
