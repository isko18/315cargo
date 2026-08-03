import pytest

from common.models import DeliveryAddress


@pytest.mark.django_db
def test_get_returns_singleton_for_any_authed(cargo_admin_client):
    r = cargo_admin_client.get("/api/delivery-address/")
    assert r.status_code == 200
    assert "recipient" in r.data and "one_line" in r.data
    # Singleton создаётся при первом обращении.
    assert DeliveryAddress.objects.count() == 1


@pytest.mark.django_db
def test_only_superuser_can_edit(cargo_admin, superuser):
    # Независимые клиенты: общий api_client в фикстурах *_client делит креды.
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    def client_for(user):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
        return c

    payload = {
        "recipient_name": "张伟",
        "phone": "+8613800138000",
        "province": "广东省",
        "city": "广州市",
        "district": "白云区",
        "detail_address": "XX路 100号 315CARGO仓库",
        "postal_code": "510000",
        "instructions": "оставьте код в имени получателя",
        "is_active": True,
    }
    # Админ карго — нельзя (403).
    r = client_for(cargo_admin).put("/api/delivery-address/", payload, format="json")
    assert r.status_code == 403

    # Супер — можно.
    r = client_for(superuser).put("/api/delivery-address/", payload, format="json")
    assert r.status_code == 200
    assert r.data["region"] == "广东省广州市白云区"

    obj = DeliveryAddress.get_solo()
    assert obj.recipient_name == "张伟"
    assert obj.updated_by_id == superuser.id


@pytest.mark.django_db
def test_client_code_embedded_in_recipient_and_one_line(auth_client, superuser_client):
    superuser_client.put(
        "/api/delivery-address/",
        {
            "recipient_name": "张伟",
            "phone": "+8613800138000",
            "province": "广东省",
            "city": "广州市",
            "district": "白云区",
            "detail_address": "XX路 100号",
            "postal_code": "510000",
        },
        format="json",
    )
    code = auth_client.user.client_code
    r = auth_client.get("/api/delivery-address/")
    assert r.status_code == 200
    # 收货人 = ТОЛЬКО код клиента (без базового имени).
    assert r.data["recipient"] == code
    assert r.data["one_line"].startswith(f"{code} ")
    assert "张伟" not in r.data["one_line"]


@pytest.mark.django_db
def test_singleton_pk_always_one():
    a = DeliveryAddress.get_solo()
    a.recipient_name = "A"
    a.save()
    b = DeliveryAddress.get_solo()
    b.recipient_name = "B"
    b.save()
    assert DeliveryAddress.objects.count() == 1
    assert DeliveryAddress.objects.first().pk == 1
