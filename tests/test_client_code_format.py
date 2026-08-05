"""Формат клиентского кода: префикс карго + 4-значный номер по возрастанию."""

import pytest
from django.contrib.auth import get_user_model

from cargo.models import CargoCompany
from tests.factories import CargoCompanyFactory, UserFactory
from users.services import generate_client_code

User = get_user_model()


@pytest.mark.django_db
def test_codes_are_sequential_and_use_cargo_prefix(cargo):
    cargo.client_code_prefix = "X"
    cargo.save()

    first = UserFactory(cargo=cargo)
    second = UserFactory(cargo=cargo)
    third = UserFactory(cargo=cargo)

    assert first.client_code == "X0001"
    assert second.client_code == "X0002"
    assert third.client_code == "X0003"

    cargo.refresh_from_db()
    assert cargo.client_code_seq == 3
    assert cargo.next_client_code() == "X0004"


@pytest.mark.django_db
def test_prefix_must_be_unique_across_cargos(cargo_admin_client, cargo):
    """Код клиента опознают в Китае, где смешаны посылки всех карго."""
    CargoCompanyFactory(slug="cargo-taken", client_code_prefix="ZZ")

    r = cargo_admin_client.patch(
        "/api/manage/cargo/", {"client_code_prefix": "zz"}, format="json"
    )
    assert r.status_code == 400
    assert "client_code_prefix" in r.data

    # Свой же префикс сохранить можно (не считается занятым).
    r = cargo_admin_client.patch(
        "/api/manage/cargo/",
        {"client_code_prefix": cargo.client_code_prefix},
        format="json",
    )
    assert r.status_code == 200, r.data


@pytest.mark.django_db
def test_prefix_may_be_multiletter_and_is_per_cargo():
    a = CargoCompanyFactory(slug="cargo-a", client_code_prefix="КК")
    b = CargoCompanyFactory(slug="cargo-b", client_code_prefix="KG1")

    assert UserFactory(cargo=a).client_code == "КК0001"
    assert UserFactory(cargo=b).client_code == "KG10001"
    # Нумерация независима: у каждого карго свой счётчик.
    assert UserFactory(cargo=a).client_code == "КК0002"


@pytest.mark.django_db
def test_prefix_change_does_not_touch_issued_codes(cargo):
    cargo.client_code_prefix = "A"
    cargo.save()
    old = UserFactory(cargo=cargo)
    assert old.client_code == "A0001"

    cargo.client_code_prefix = "B"
    cargo.save()
    new = UserFactory(cargo=cargo)

    old.refresh_from_db()
    assert old.client_code == "A0001"  # выданный код не пересчитывается
    assert new.client_code == "B0002"  # нумерация продолжается сквозной


@pytest.mark.django_db
def test_taken_number_is_skipped(cargo):
    cargo.client_code_prefix = "X"
    cargo.save()
    # Код X0001 уже занят вручную (напр. правка в админке).
    UserFactory(cargo=cargo, client_code="X0001")

    assert generate_client_code(cargo) == "X0002"


@pytest.mark.django_db
def test_owner_can_change_prefix_and_see_preview(cargo_admin_client, cargo):
    # Сам админ карго — тоже пользователь, его код уже занял первый номер.
    cargo.refresh_from_db()
    nxt = cargo.client_code_seq + 1

    r = cargo_admin_client.get("/api/manage/cargo/")
    assert r.status_code == 200
    assert r.data["client_code_prefix"] == cargo.client_code_prefix
    assert r.data["client_code_next"] == f"{cargo.client_code_prefix}{nxt:04d}"

    r = cargo_admin_client.patch(
        "/api/manage/cargo/", {"client_code_prefix": " X "}, format="json"
    )
    assert r.status_code == 200, r.data
    assert r.data["client_code_prefix"] == "X"
    assert r.data["client_code_next"] == f"X{nxt:04d}"  # нумерация продолжается
    cargo.refresh_from_db()
    assert cargo.client_code_prefix == "X"
    assert cargo.client_code_seq == nxt - 1  # правка префикса счётчик не двигает


@pytest.mark.django_db
@pytest.mark.parametrize("bad", ["", "  ", "X Y", "X-1", "TOOLONGG"])
def test_bad_prefix_rejected(cargo_admin_client, bad):
    r = cargo_admin_client.patch(
        "/api/manage/cargo/", {"client_code_prefix": bad}, format="json"
    )
    assert r.status_code == 400
    assert "client_code_prefix" in r.data


@pytest.mark.django_db
def test_owner_cannot_shift_counter(cargo_admin_client, cargo):
    """Счётчик только на чтение — иначе можно переиспользовать чужие коды."""
    UserFactory(cargo=cargo)
    cargo.refresh_from_db()
    before = cargo.client_code_seq

    r = cargo_admin_client.patch(
        "/api/manage/cargo/", {"client_code_seq": 0}, format="json"
    )
    assert r.status_code == 200
    cargo.refresh_from_db()
    assert cargo.client_code_seq == before


@pytest.mark.django_db
def test_super_owner_sets_prefix_on_create(superuser_client):
    r = superuser_client.post(
        "/api/admin/cargos/",
        {
            "title": "Карго Префикс",
            "slug": "cargo-prefix",
            "client_code_prefix": "KK",
            "owner_name": "Владелец",
            "owner_phone": "+996700123150",
            "owner_password": "ownerpw1",
        },
        format="json",
    )
    assert r.status_code == 201, r.data
    assert r.data["cargo"]["client_code_prefix"] == "KK"

    created = CargoCompany.objects.get(slug="cargo-prefix")
    owner = User.objects.get(phone="+996700123150", cargo=created)
    assert owner.client_code == "KK0001"  # владелец занял первый номер
    assert r.data["cargo"]["client_code_next"] == "KK0002"
    assert UserFactory(cargo=created).client_code == "KK0002"


@pytest.mark.django_db
def test_user_without_cargo_still_gets_code():
    """Служебные пользователи без карго — прежняя случайная схема, без счётчика."""
    code = generate_client_code(None)
    assert code.startswith("C") and len(code) == 8
