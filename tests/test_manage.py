import pytest

from city_delivery.models import CityDeliveryTariff
from pickup_points.models import PickupPoint
from tests.factories import CargoCompanyFactory, PickupPointFactory


@pytest.mark.django_db
def test_owner_can_create_pickup_point(cargo_admin_client):
    response = cargo_admin_client.post(
        "/api/manage/pickup-points/",
        {"title": "Новый ПВЗ", "address": "Бишкек, ул. 1"},
        format="json",
    )
    assert response.status_code == 201
    point = PickupPoint.objects.get(id=response.data["id"])
    assert point.cargo_id == cargo_admin_client.user.cargo_id


@pytest.mark.django_db
def test_owner_sees_only_own_pickup_points(cargo_admin_client):
    PickupPointFactory(cargo=cargo_admin_client.user.cargo, title="Свой")
    PickupPointFactory(cargo=CargoCompanyFactory(), title="Чужой")
    response = cargo_admin_client.get("/api/manage/pickup-points/")
    items = (
        response.data["results"]
        if isinstance(response.data, dict) and "results" in response.data
        else response.data
    )
    cargo_ids = {i["cargo"] for i in items}
    assert cargo_ids == {cargo_admin_client.user.cargo_id}


@pytest.mark.django_db
def test_owner_cannot_edit_foreign_pickup_point(cargo_admin_client):
    foreign = PickupPointFactory(cargo=CargoCompanyFactory())
    response = cargo_admin_client.patch(
        f"/api/manage/pickup-points/{foreign.id}/",
        {"title": "Взлом"},
        format="json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_client_cannot_manage_pickup_points(auth_client):
    response = auth_client.post(
        "/api/manage/pickup-points/",
        {"title": "X", "address": "Y"},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_owner_can_create_tariff(cargo_admin_client):
    response = cargo_admin_client.post(
        "/api/manage/city-delivery-tariffs/",
        {"title": "Тариф", "base_price": "100.00", "price_per_kg": "20.00"},
        format="json",
    )
    assert response.status_code == 201
    tariff = CityDeliveryTariff.objects.get(id=response.data["id"])
    assert tariff.cargo_id == cargo_admin_client.user.cargo_id


@pytest.mark.django_db
def test_owner_can_update_cargo_profile(cargo_admin_client):
    response = cargo_admin_client.patch(
        "/api/manage/cargo/", {"phone": "+996555111222"}, format="json"
    )
    assert response.status_code == 200
    assert response.data["phone"] == "+996555111222"
    cargo_admin_client.user.cargo.refresh_from_db()
    assert cargo_admin_client.user.cargo.phone == "+996555111222"


@pytest.mark.django_db
def test_cargo_dashboard_counts_only_own(cargo_admin_client):
    from tests.factories import ParcelFactory, UserFactory

    cargo = cargo_admin_client.user.cargo
    client = UserFactory(cargo=cargo)
    ParcelFactory(user=client, cargo=cargo)
    ParcelFactory()  # another cargo

    response = cargo_admin_client.get("/api/manage/dashboard/")
    assert response.status_code == 200
    assert response.data["parcels_count"] == 1
    assert response.data["cargo"]["id"] == cargo.id
