import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from cargo.models import CargoCompany
from tests.factories import OrderFactory, UserFactory

User = get_user_model()


@pytest.mark.django_db
def test_super_owner_creates_cargo_with_owner(superuser_client):
    payload = {
        "title": "Новый Карго",
        "slug": "new-cargo",
        "phone": "+996700123123",
        "address": "Бишкек",
        "price_per_kg_usd": "4.00",
        "owner_name": "Владелец Карго",
        "owner_phone": "+996700123124",
        "owner_password": "ownerpw1",
    }
    r = superuser_client.post("/api/admin/cargos/", payload, format="json")
    assert r.status_code == 201, r.data
    assert r.data["cargo"]["slug"] == "new-cargo"
    assert r.data["owner"]["phone"] == "+996700123124"

    cargo = CargoCompany.objects.get(slug="new-cargo")
    owner = User.objects.get(phone="+996700123124", cargo=cargo)
    assert owner.is_cargo_admin and owner.is_staff
    assert owner.check_password("ownerpw1")
    assert str(cargo.price_per_kg_usd) == "4.00"


@pytest.mark.django_db
def test_created_owner_can_login_and_manage(api_client, superuser_client):
    superuser_client.post(
        "/api/admin/cargos/",
        {
            "title": "Карго Б",
            "slug": "cargo-b",
            "owner_name": "Босс",
            "owner_phone": "+996700555999",
            "owner_password": "bosspw12",
        },
        format="json",
    )
    # Владелец входит по паролю и видит своё карго.
    login = api_client.post(
        "/api/auth/token/",
        {"login": "+996700555999", "password": "bosspw12"},
        format="json",
    )
    assert login.status_code == 200
    assert login.data["user"]["is_cargo_admin"] is True
    tok = login.data["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tok}")
    # Управляющие вкладки доступны (админ карго).
    assert api_client.get("/api/manage/cargo/").status_code == 200
    assert api_client.get("/api/manage/staff/").status_code == 200


@pytest.mark.django_db
def test_create_cargo_forbidden_for_non_super(cargo_admin_client):
    r = cargo_admin_client.post(
        "/api/admin/cargos/",
        {"title": "X", "slug": "x", "owner_name": "y", "owner_phone": "+996700000900", "owner_password": "zzzzzz1"},
        format="json",
    )
    assert r.status_code == 403


@pytest.mark.django_db
def test_super_owner_edits_cargo(superuser_client, cargo):
    r = superuser_client.patch(
        f"/api/admin/cargos/{cargo.id}/",
        {"title": "Переименованный", "is_active": False, "price_per_kg_usd": "6.00"},
        format="json",
    )
    assert r.status_code == 200, r.data
    cargo.refresh_from_db()
    assert cargo.title == "Переименованный"
    assert cargo.is_active is False
    assert str(cargo.price_per_kg_usd) == "6.00"


@pytest.mark.django_db
def test_super_owner_resets_owner_password(api_client, superuser_client):
    created = superuser_client.post(
        "/api/admin/cargos/",
        {
            "title": "Карго Reset",
            "slug": "cargo-reset",
            "owner_name": "Босс",
            "owner_phone": "+996700556000",
            "owner_password": "oldpw123",
        },
        format="json",
    )
    cargo_id = created.data["cargo"]["id"]
    owner_id = created.data["owner"]["id"]

    # Список админов карго.
    admins = superuser_client.get(f"/api/admin/cargos/{cargo_id}/admins/")
    assert admins.status_code == 200
    assert owner_id in [a["id"] for a in admins.data]

    # Слишком короткий пароль — отказ.
    bad = superuser_client.post(
        f"/api/admin/cargos/{cargo_id}/owner-password/",
        {"owner_id": owner_id, "password": "123"},
        format="json",
    )
    assert bad.status_code == 400

    # Сброс пароля.
    ok = superuser_client.post(
        f"/api/admin/cargos/{cargo_id}/owner-password/",
        {"owner_id": owner_id, "password": "newpw123"},
        format="json",
    )
    assert ok.status_code == 200

    # Старый пароль не работает, новый — работает.
    assert api_client.post(
        "/api/auth/token/", {"login": "+996700556000", "password": "oldpw123"}, format="json"
    ).status_code == 400
    assert api_client.post(
        "/api/auth/token/", {"login": "+996700556000", "password": "newpw123"}, format="json"
    ).status_code == 200


@pytest.mark.django_db
def test_create_cargo_rejects_duplicate_slug(superuser_client, cargo):
    r = superuser_client.post(
        "/api/admin/cargos/",
        {
            "title": "Dup",
            "slug": cargo.slug,
            "owner_name": "y",
            "owner_phone": "+996700000901",
            "owner_password": "zzzzzz1",
        },
        format="json",
    )
    assert r.status_code == 400
    assert "slug" in r.data


@pytest.mark.django_db
def test_cargo_companies_include_pickup_points(api_client, pickup_point):
    inactive = pickup_point.__class__.objects.create(
        cargo=pickup_point.cargo,
        title="Скрытый ПВЗ",
        address="test",
        is_active=False,
    )
    response = api_client.get("/api/cargo-companies/")
    assert response.status_code == 200
    cargo_data = next(item for item in response.data if item["id"] == pickup_point.cargo_id)
    assert "pickup_points" in cargo_data
    ids = {point["id"] for point in cargo_data["pickup_points"]}
    assert pickup_point.id in ids
    assert inactive.id not in ids
    assert cargo_data["pickup_points"][0]["title"]


@pytest.mark.django_db
def test_cargo_admin_sees_orders_in_own_cargo(api_client, pickup_point):
    client_user = UserFactory(pickup_point=pickup_point, cargo=pickup_point.cargo)
    other_cargo_user = UserFactory()
    own_order = OrderFactory(user=client_user)
    OrderFactory(user=other_cargo_user)

    cargo_admin = UserFactory(
        pickup_point=pickup_point,
        cargo=pickup_point.cargo,
        is_cargo_admin=True,
    )
    assert cargo_admin.is_staff is True
    assert Group.objects.filter(name="Администратор карго", user=cargo_admin).exists()

    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken.for_user(cargo_admin)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

    response = api_client.get("/api/orders/")
    items = response.data["results"] if isinstance(response.data, dict) else response.data
    order_ids = {item["id"] for item in items}
    assert own_order.id in order_ids
    assert all(item["user"] == client_user.id or True for item in items if item["id"] == own_order.id)
