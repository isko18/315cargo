import pytest

from tests.factories import ParcelFactory, PickupPointFactory, UserFactory


@pytest.mark.django_db
def test_admin_overview_requires_superuser(cargo_admin_client):
    response = cargo_admin_client.get("/api/admin/overview/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_overview_returns_totals_and_per_cargo(superuser_client):
    client = UserFactory()
    cargo = client.cargo
    PickupPointFactory(cargo=cargo)
    ParcelFactory(user=client, cargo=cargo)

    response = superuser_client.get("/api/admin/overview/")
    assert response.status_code == 200

    totals = response.data["totals"]
    assert totals["cargo_count"] >= 1
    assert totals["user_count"] >= 1
    assert totals["parcel_count"] >= 1
    assert totals["pickup_point_count"] >= 1

    item = next(c for c in response.data["per_cargo"] if c["id"] == cargo.id)
    assert item["users_count"] == 1
    assert item["parcels_count"] == 1
    assert item["pickup_points_count"] >= 1
