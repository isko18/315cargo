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
def test_recipient_comes_from_client_cargo(user, superuser_client):
    """У каждого карго свой человек на приёмке — ФИО берётся из карго клиента."""
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    superuser_client.put(
        "/api/delivery-address/",
        {
            "recipient_name": "Общий Запасной",
            "phone": "13250150777",
            "province": "广东",
            "detail_address": "里水镇和顺鹤峰1号仓315库",
            "postal_code": "528241",
        },
        format="json",
    )
    cargo = user.cargo
    cargo.recipient_name = "张伟"
    cargo.code = "x69610"
    cargo.save()

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    r = client.get("/api/delivery-address/")

    assert r.status_code == 200
    assert r.data["recipient"] == "张伟"  # не «Общий Запасной»
    assert r.data["one_line"].startswith("张伟 ")


@pytest.mark.django_db
def test_global_recipient_is_fallback_when_cargo_has_none(user, superuser_client):
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    superuser_client.put(
        "/api/delivery-address/",
        {
            "recipient_name": "Общий Запасной",
            "phone": "13250150777",
            "province": "广东",
            "detail_address": "里水镇",
            "postal_code": "528241",
        },
        format="json",
    )
    assert user.cargo.recipient_name == ""  # у карго ФИО не задано

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    r = client.get("/api/delivery-address/")

    assert r.data["recipient"] == "Общий Запасной"


@pytest.mark.django_db
def test_cargo_code_goes_before_client_code(user, superuser_client):
    """Код карго — общий для клиентов карго, стоит перед личным кодом клиента."""
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    superuser_client.put(
        "/api/delivery-address/",
        {
            "recipient_name": "张伟",
            "phone": "13250150777",
            "province": "广东",
            "city": "佛山",
            "district": "南海",
            "detail_address": "里水镇和顺鹤峰1号仓315库",
            "postal_code": "528241",
        },
        format="json",
    )
    cargo = user.cargo
    cargo.code = "x69610"
    cargo.save()

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")

    code = user.client_code
    r = client.get("/api/delivery-address/")
    assert r.status_code == 200
    assert r.data["cargo_code"] == "x69610"
    assert r.data["one_line"] == (
        f"张伟 13250150777 广东佛山南海 里水镇和顺鹤峰1号仓315库 x69610 {code}"
    )


@pytest.mark.django_db
def test_cargo_address_suffix_glued_to_detail(user, superuser_client):
    """Приписка карго клеится к адресу слитно, индекса в строке нет."""
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    superuser_client.put(
        "/api/delivery-address/",
        {
            "recipient_name": "",
            "phone": "13250150777",
            "province": "广东",
            "city": "佛山",
            "district": "南海",
            "detail_address": "里水镇和顺鹤峰1号仓315库",
        },
        format="json",
    )
    cargo = user.cargo
    cargo.recipient_name = "程先生"
    cargo.code = "x69610"
    cargo.address_suffix = "东"
    cargo.save()

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    r = client.get("/api/delivery-address/")

    code = user.client_code
    assert r.data["one_line"] == (
        f"程先生 13250150777 广东佛山南海 里水镇和顺鹤峰1号仓315库东 x69610 {code}"
    )
    # Полный детальный адрес — для ручного заполнения полей в PDD.
    assert r.data["detail_address_full"] == "里水镇和顺鹤峰1号仓315库东"
    # Индекса нет ни в строке, ни в ответе.
    assert "postal_code" not in r.data


@pytest.mark.django_db
def test_one_line_starts_with_name_and_ends_with_client_code(auth_client, superuser_client):
    superuser_client.put(
        "/api/delivery-address/",
        {
            "recipient_name": "张伟",
            "phone": "+8613800138000",
            "province": "广东省",
            "city": "广州市",
            "district": "白云区",
            "detail_address": "XX路100号",
            "postal_code": "510000",
        },
        format="json",
    )
    code = auth_client.user.client_code
    r = auth_client.get("/api/delivery-address/")
    assert r.status_code == 200
    # 收货人 = ФИО; код клиента — в самом конце строки.
    assert r.data["recipient"] == "张伟"
    assert r.data["one_line"] == (
        f"张伟 +8613800138000 广东省广州市白云区 XX路100号 {code}"
    )


@pytest.mark.django_db
def test_code_not_duplicated_when_name_empty(auth_client, superuser_client):
    """Без ФИО получателем становится код — второй раз его не добавляем."""
    superuser_client.put(
        "/api/delivery-address/",
        {
            "recipient_name": "",
            "phone": "+8613800138000",
            "province": "广东省",
            "city": "",
            "district": "",
            "detail_address": "XX路100号",
            "postal_code": "510000",
        },
        format="json",
    )
    code = auth_client.user.client_code
    r = auth_client.get("/api/delivery-address/")
    assert r.data["recipient"] == code
    assert r.data["one_line"] == f"{code} +8613800138000 广东省 XX路100号"


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
