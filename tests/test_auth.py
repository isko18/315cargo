import pytest
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from tests.factories import CargoCompanyFactory, PickupPointFactory
from users.models import SMSCode

User = get_user_model()


@pytest.mark.django_db
def test_send_code_creates_sms(api_client, cargo):
    response = api_client.post(
        "/api/auth/send-code/",
        {"phone": "+996700111111", "cargo_id": cargo.id, "purpose": "register"},
        format="json",
    )
    assert response.status_code == 200
    assert SMSCode.objects.filter(phone="+996700111111").exists()


@pytest.mark.django_db
def test_send_code_throttled(api_client, cargo):
    payload = {"phone": "+996700222222", "cargo_id": cargo.id, "purpose": "register"}
    api_client.post("/api/auth/send-code/", payload, format="json")
    response = api_client.post("/api/auth/send-code/", payload, format="json")
    assert response.status_code == 429


@pytest.mark.django_db
def test_register_and_login_with_pickup_point(api_client, pickup_point):
    phone = "+996700333333"
    api_client.post(
        "/api/auth/send-code/",
        {
            "phone": phone,
            "cargo_id": pickup_point.cargo_id,
            "purpose": "register",
        },
        format="json",
    )
    sms = SMSCode.objects.get(phone=phone)

    response = api_client.post(
        "/api/auth/verify-code/",
        {
            "phone": phone,
            "code": sms.code,
            "cargo_id": pickup_point.cargo_id,
            "pickup_point_id": pickup_point.id,
            "full_name": "Тест Тестов",
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    body = response.data
    assert body["is_new_user"] is True
    assert body["user"]["client_code"]
    assert body["user"]["pickup_point"] == pickup_point.id
    assert body["user"]["cargo"] == pickup_point.cargo_id
    assert body["access"]
    assert body["refresh"]


@pytest.mark.django_db
def test_same_phone_different_cargos(api_client):
    cargo_a = CargoCompanyFactory(slug="cargo-a")
    cargo_b = CargoCompanyFactory(slug="cargo-b")
    pp_a = PickupPointFactory(cargo=cargo_a)
    pp_b = PickupPointFactory(cargo=cargo_b)
    phone = "+996700444444"

    api_client.post(
        "/api/auth/send-code/",
        {"phone": phone, "cargo_id": cargo_a.id, "purpose": "register"},
        format="json",
    )
    sms = SMSCode.objects.filter(phone=phone, is_used=False).latest("created_at")
    response = api_client.post(
        "/api/auth/verify-code/",
        {
            "phone": phone,
            "code": sms.code,
            "cargo_id": cargo_a.id,
            "pickup_point_id": pp_a.id,
            "full_name": "Клиент A",
        },
        format="json",
    )
    assert response.status_code == 200, response.data

    SMSCode.objects.filter(phone=phone).update(
        created_at=timezone.now() - timedelta(seconds=61)
    )
    api_client.post(
        "/api/auth/send-code/",
        {"phone": phone, "cargo_id": cargo_b.id, "purpose": "register"},
        format="json",
    )
    sms = SMSCode.objects.filter(phone=phone, is_used=False).latest("created_at")
    response = api_client.post(
        "/api/auth/verify-code/",
        {
            "phone": phone,
            "code": sms.code,
            "cargo_id": cargo_b.id,
            "pickup_point_id": pp_b.id,
            "full_name": "Клиент B",
        },
        format="json",
    )
    assert response.status_code == 200, response.data

    assert User.objects.filter(phone=phone).count() == 2


@pytest.mark.django_db
def test_existing_user_login(api_client, user):
    api_client.post(
        "/api/auth/send-code/",
        {"phone": user.phone, "cargo_id": user.cargo_id, "purpose": "login"},
        format="json",
    )
    sms = SMSCode.objects.get(phone=user.phone)
    response = api_client.post(
        "/api/auth/verify-code/",
        {"phone": user.phone, "code": sms.code, "cargo_id": user.cargo_id},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["is_new_user"] is False
    assert response.data["user"]["id"] == user.id


@pytest.mark.django_db
def test_refresh_token(api_client, user):
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(user)
    response = api_client.post(
        "/api/auth/refresh/", {"refresh": str(refresh)}, format="json"
    )
    assert response.status_code == 200
    assert "access" in response.data


@pytest.mark.django_db
def test_logout_blacklists_refresh(api_client, user):
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    response = api_client.post(
        "/api/auth/logout/", {"refresh": str(refresh)}, format="json"
    )
    assert response.status_code == 204

    response = api_client.post(
        "/api/auth/refresh/", {"refresh": str(refresh)}, format="json"
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_cargo_companies_list(api_client, cargo):
    response = api_client.get("/api/cargo-companies/")
    assert response.status_code == 200
    assert any(item["id"] == cargo.id for item in response.data)


@pytest.mark.django_db
def test_pickup_points_public_list(api_client, pickup_point):
    response = api_client.get(f"/api/pickup-points/?cargo={pickup_point.cargo_id}")
    assert response.status_code == 200
    assert any(item["id"] == pickup_point.id for item in response.data)
