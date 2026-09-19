"""Единый вход по SMS-коду: сотрудник заходит той же дверью, что и клиент.

Опаснее всего здесь не отказ во входе, а тихий неверный ответ: при
is_new_user=true приложение уводит существующего сотрудника на анкету
регистрации и заводит ему клиентский дубль поверх служебного аккаунта.
Поэтому check-code и verify-code обязаны отвечать одинаково — оба ходят в
один резолвер, и тесты держат их вместе.

Клиентский вход — путь тысяч людей, он не должен измениться ни на шаг:
половина файла именно об этом.
"""

import pytest
from django.contrib.auth import get_user_model

from tests.factories import CargoCompanyFactory, PickupPointFactory, UserFactory
from users.models import SMSCode
from users.services import send_sms_code

User = get_user_model()


def code_for(phone, cargo):
    """Последний выданный код — как если бы он пришёл в SMS."""
    return SMSCode.objects.filter(phone=phone, cargo=cargo).order_by("-created_at").first().code


@pytest.fixture
def staff(db, cargo):
    return User.objects.create(
        phone="+996700111222",
        cargo=cargo,
        full_name="Тест Оператор",
        is_staff=True,
        is_cargo_admin=True,
    )


# --- Сотрудник ---


@pytest.mark.django_db
def test_send_code_accepts_staff_phone(api_client, cargo, staff):
    """У сотрудника может не быть клиентского профиля вовсе."""
    r = api_client.post(
        "/api/auth/send-code/",
        {"phone": staff.phone, "cargo_id": cargo.id, "purpose": "login"},
        format="json",
    )
    assert r.status_code == 200


@pytest.mark.django_db
def test_check_code_says_staff_is_not_new(api_client, cargo, staff):
    """is_new_user=true увёл бы сотрудника на регистрацию клиента."""
    send_sms_code(staff.phone, cargo=cargo)

    r = api_client.post(
        "/api/auth/check-code/",
        {"phone": staff.phone, "code": code_for(staff.phone, cargo), "cargo_id": cargo.id},
        format="json",
    )

    assert r.status_code == 200
    assert r.data["is_new_user"] is False


@pytest.mark.django_db
def test_verify_code_returns_staff_session_with_role_flags(api_client, cargo, staff):
    """Без флагов сотрудник войдёт, но приложение откроет клиентскую часть."""
    send_sms_code(staff.phone, cargo=cargo)

    r = api_client.post(
        "/api/auth/verify-code/",
        {"phone": staff.phone, "code": code_for(staff.phone, cargo), "cargo_id": cargo.id},
        format="json",
    )

    assert r.status_code == 200
    assert r.data["is_new_user"] is False
    user = r.data["user"]
    assert user["id"] == staff.id
    assert user["is_staff"] is True
    assert user["is_cargo_admin"] is True
    assert user["is_china_staff"] is False
    assert user["is_superuser"] is False
    assert isinstance(user["allowed_tabs"], list)


@pytest.mark.django_db
def test_staff_login_creates_no_client_duplicate(api_client, cargo, staff):
    send_sms_code(staff.phone, cargo=cargo)
    api_client.post(
        "/api/auth/verify-code/",
        {"phone": staff.phone, "code": code_for(staff.phone, cargo), "cargo_id": cargo.id},
        format="json",
    )

    assert User.objects.filter(phone=staff.phone).count() == 1


@pytest.mark.django_db
def test_profile_keeps_role_flags(api_client, cargo, staff):
    send_sms_code(staff.phone, cargo=cargo)
    tokens = api_client.post(
        "/api/auth/verify-code/",
        {"phone": staff.phone, "code": code_for(staff.phone, cargo), "cargo_id": cargo.id},
        format="json",
    ).data
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    r = api_client.get("/api/profile/")

    assert r.status_code == 200
    assert (r.data["is_staff"], r.data["is_cargo_admin"]) == (True, True)


@pytest.mark.django_db
def test_staff_pickup_is_not_overwritten_by_registration_form(api_client, cargo, staff):
    """ПВЗ сотрудника — место работы, анкета входа его менять не должна."""
    his = PickupPointFactory(cargo=cargo)
    other = PickupPointFactory(cargo=cargo)
    staff.pickup_point = his
    staff.save(update_fields=["pickup_point"])
    send_sms_code(staff.phone, cargo=cargo)

    api_client.post(
        "/api/auth/verify-code/",
        {
            "phone": staff.phone,
            "code": code_for(staff.phone, cargo),
            "cargo_id": cargo.id,
            "pickup_point_id": other.id,
            "full_name": "Подмена",
        },
        format="json",
    )

    staff.refresh_from_db()
    assert staff.pickup_point_id == his.id
    assert staff.full_name == "Тест Оператор"


@pytest.mark.django_db
def test_staff_of_one_cargo_is_separate_from_client_of_another(api_client, cargo, staff):
    """Один номер: оператор карго A и клиент карго B — разные аккаунты."""
    other_cargo = CargoCompanyFactory()
    client = UserFactory(
        cargo=other_cargo,
        pickup_point=PickupPointFactory(cargo=other_cargo),
        phone=staff.phone,
    )
    send_sms_code(staff.phone, cargo=cargo)

    r = api_client.post(
        "/api/auth/verify-code/",
        {"phone": staff.phone, "code": code_for(staff.phone, cargo), "cargo_id": cargo.id},
        format="json",
    )

    # В своём карго номер — это оператор, а не клиент другого карго.
    assert r.data["user"]["id"] == staff.id
    assert r.data["user"]["id"] != client.id


# --- Клиенты: ничего не поменялось ---


@pytest.mark.django_db
def test_existing_client_logs_in_as_before(api_client, cargo):
    client = UserFactory(cargo=cargo, pickup_point=PickupPointFactory(cargo=cargo))
    send_sms_code(client.phone, cargo=cargo)
    code = code_for(client.phone, cargo)

    check = api_client.post(
        "/api/auth/check-code/",
        {"phone": client.phone, "code": code, "cargo_id": cargo.id},
        format="json",
    )
    assert check.data["is_new_user"] is False

    r = api_client.post(
        "/api/auth/verify-code/",
        {"phone": client.phone, "code": code, "cargo_id": cargo.id},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["user"]["id"] == client.id
    assert r.data["user"]["is_staff"] is False


@pytest.mark.django_db
def test_new_client_registers_as_before(api_client, cargo):
    point = PickupPointFactory(cargo=cargo)
    phone = "+996709998877"
    send_sms_code(phone, cargo=cargo, purpose=SMSCode.Purpose.REGISTER)
    code = code_for(phone, cargo)

    check = api_client.post(
        "/api/auth/check-code/",
        {"phone": phone, "code": code, "cargo_id": cargo.id},
        format="json",
    )
    assert check.data["is_new_user"] is True

    r = api_client.post(
        "/api/auth/verify-code/",
        {
            "phone": phone,
            "code": code,
            "cargo_id": cargo.id,
            "pickup_point_id": point.id,
            "full_name": "Новый Клиент",
        },
        format="json",
    )

    assert r.status_code == 200
    assert r.data["is_new_user"] is True
    assert r.data["user"]["client_code"]
    assert r.data["user"]["pickup_point"] == point.id


@pytest.mark.django_db
def test_check_code_still_does_not_burn_the_code(api_client, cargo):
    """Если начнёт гасить — сломается вся регистрация: verify-code следом."""
    point = PickupPointFactory(cargo=cargo)
    phone = "+996709998878"
    send_sms_code(phone, cargo=cargo, purpose=SMSCode.Purpose.REGISTER)
    code = code_for(phone, cargo)

    api_client.post(
        "/api/auth/check-code/",
        {"phone": phone, "code": code, "cargo_id": cargo.id},
        format="json",
    )
    r = api_client.post(
        "/api/auth/verify-code/",
        {
            "phone": phone,
            "code": code,
            "cargo_id": cargo.id,
            "pickup_point_id": point.id,
            "full_name": "Ещё Клиент",
        },
        format="json",
    )

    assert r.status_code == 200


# --- Пароль сотрудника ---


@pytest.mark.django_db
def test_staff_can_be_created_without_password(cargo_admin_client):
    r = cargo_admin_client.post(
        "/api/manage/staff/",
        {"phone": "+996700333444", "full_name": "Без пароля", "is_cargo_admin": False},
        format="json",
    )

    assert r.status_code == 201
    created = User.objects.get(phone="+996700333444")
    assert created.is_staff
    # Непригодный пароль, а не пустой: пустой прошёл бы вход по паролю.
    assert not created.has_usable_password()


@pytest.mark.django_db
def test_password_login_still_works_for_those_who_have_one(api_client, cargo_admin_client, cargo):
    """auth/token/ остаётся страховкой на релиз — удалять его рано."""
    cargo_admin_client.post(
        "/api/manage/staff/",
        {"phone": "+996700555666", "full_name": "С паролем", "password": "secret123"},
        format="json",
    )

    r = api_client.post(
        "/api/auth/token/", {"login": "+996700555666", "password": "secret123"}, format="json"
    )

    assert r.status_code == 200
    assert r.data["access"]
