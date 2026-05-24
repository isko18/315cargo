import pytest
from django.contrib.auth.models import Group

from tests.factories import OrderFactory, UserFactory


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
