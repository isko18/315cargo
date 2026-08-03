import pytest

from city_delivery.models import CityDeliveryRequest
from parcels.models import Parcel
from tests.factories import (
    CityDeliveryRequestFactory,
    OrderFactory,
    ParcelFactory,
    UserFactory,
)


def _items(r):
    return r.data["results"] if isinstance(r.data, dict) and "results" in r.data else r.data


@pytest.mark.django_db
def test_clients_list_and_history(cargo_admin_client):
    cargo = cargo_admin_client.user.cargo
    client = UserFactory(cargo=cargo, full_name="Иван Клиент")
    OrderFactory(user=client, product_title="Куртка")
    ParcelFactory(user=client, cargo=cargo)

    r = cargo_admin_client.get("/api/manage/clients/")
    assert r.status_code == 200
    row = next(c for c in _items(r) if c["id"] == client.id)
    assert row["full_name"] == "Иван Клиент"
    assert row["orders_count"] == 1
    assert row["parcels_count"] == 1

    h = cargo_admin_client.get(f"/api/manage/clients/{client.id}/history/")
    assert h.status_code == 200
    assert len(h.data["orders"]) == 1
    assert len(h.data["parcels"]) == 1
    assert h.data["client"]["full_name"] == "Иван Клиент"


@pytest.mark.django_db
def test_clients_scoped_to_cargo(cargo_admin_client):
    cargo = cargo_admin_client.user.cargo
    mine = UserFactory(cargo=cargo)
    other = UserFactory()  # другое карго
    r = cargo_admin_client.get("/api/manage/clients/")
    ids = [c["id"] for c in _items(r)]
    assert mine.id in ids
    assert other.id not in ids


@pytest.mark.django_db
def test_operator_without_clients_tab_forbidden(api_client, cargo):
    from rest_framework_simplejwt.tokens import RefreshToken

    op = UserFactory(cargo=cargo, is_staff=True, allowed_tabs=["warehouse"])
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(op).access_token}")
    assert api_client.get("/api/manage/clients/").status_code == 403


@pytest.mark.django_db
def test_delivery_request_status_update_syncs_parcel(cargo_admin_client):
    cargo = cargo_admin_client.user.cargo
    client = UserFactory(cargo=cargo)
    parcel = ParcelFactory(user=client, cargo=cargo, status=Parcel.Status.AT_PICKUP_POINT)
    req = CityDeliveryRequestFactory(user=client, parcel=parcel)

    r = cargo_admin_client.patch(
        f"/api/manage/city-delivery/{req.id}/",
        {"status": CityDeliveryRequest.Status.DELIVERED},
        format="json",
    )
    assert r.status_code == 200, r.data
    req.refresh_from_db()
    parcel.refresh_from_db()
    assert req.status == CityDeliveryRequest.Status.DELIVERED
    assert req.delivered_at is not None
    assert parcel.status == Parcel.Status.DELIVERED


@pytest.mark.django_db
def test_delivery_requests_scoped_to_cargo(cargo_admin_client):
    cargo = cargo_admin_client.user.cargo
    mine = CityDeliveryRequestFactory(
        user=UserFactory(cargo=cargo),
        parcel=ParcelFactory(cargo=cargo),
    )
    CityDeliveryRequestFactory()  # другое карго
    r = cargo_admin_client.get("/api/manage/city-delivery/")
    ids = [x["id"] for x in _items(r)]
    assert mine.id in ids
    assert len(ids) == 1
