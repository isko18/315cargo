import pytest

from orders.models import Order
from parcels.models import Parcel
from tests.factories import OrderFactory, ParcelFactory, UserFactory


@pytest.mark.django_db
def test_scan_unknown_track_creates_pending(cargo_admin_client):
    response = cargo_admin_client.post(
        "/api/parcels/scan/", {"track_number": "NEWTRACK001"}, format="json"
    )
    assert response.status_code == 201
    assert response.data["result"] == "created_pending"
    parcel = Parcel.objects.get(track_number="NEWTRACK001")
    assert parcel.user_id is None
    assert parcel.cargo_id == cargo_admin_client.user.cargo_id
    assert parcel.status == Parcel.Status.ARRIVED_CHINA_WAREHOUSE


@pytest.mark.django_db
def test_scan_existing_parcel_advances_status(cargo_admin_client):
    cargo = cargo_admin_client.user.cargo
    client = UserFactory(cargo=cargo)
    parcel = ParcelFactory(user=client, cargo=cargo, status=Parcel.Status.CREATED)

    response = cargo_admin_client.post(
        "/api/parcels/scan/", {"track_number": parcel.track_number}, format="json"
    )
    assert response.status_code == 200
    assert response.data["result"] == "updated"
    parcel.refresh_from_db()
    assert parcel.status == Parcel.Status.ARRIVED_CHINA_WAREHOUSE
    assert parcel.history.filter(status=Parcel.Status.ARRIVED_CHINA_WAREHOUSE).exists()


@pytest.mark.django_db
def test_scan_matches_order(cargo_admin_client):
    cargo = cargo_admin_client.user.cargo
    client = UserFactory(cargo=cargo)
    order = OrderFactory(user=client, track_number="ORDTRACK001")

    response = cargo_admin_client.post(
        "/api/parcels/scan/", {"track_number": "ORDTRACK001"}, format="json"
    )
    assert response.status_code == 201
    assert response.data["result"] == "created_from_order"
    parcel = Parcel.objects.get(track_number="ORDTRACK001")
    assert parcel.user_id == client.id
    assert parcel.order_id == order.id


@pytest.mark.django_db
def test_scan_cross_cargo_conflict(cargo_admin_client):
    other_parcel = ParcelFactory()  # parcel in a different cargo
    response = cargo_admin_client.post(
        "/api/parcels/scan/",
        {"track_number": other_parcel.track_number},
        format="json",
    )
    assert response.status_code == 409
    assert response.data["code"] == "conflict"


@pytest.mark.django_db
def test_scan_forbidden_for_client(auth_client):
    response = auth_client.post(
        "/api/parcels/scan/", {"track_number": "NEWTRACK002"}, format="json"
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_assign_pending_parcel_to_client(cargo_admin_client):
    cargo = cargo_admin_client.user.cargo
    client = UserFactory(cargo=cargo)
    parcel = Parcel.objects.create(cargo=cargo, track_number="PENDING001")

    response = cargo_admin_client.post(
        f"/api/parcels/{parcel.id}/assign/",
        {"client_code": client.client_code},
        format="json",
    )
    assert response.status_code == 200
    parcel.refresh_from_db()
    assert parcel.user_id == client.id
    assert parcel.client_code == client.client_code


@pytest.mark.django_db
def test_assign_unknown_client_code(cargo_admin_client):
    cargo = cargo_admin_client.user.cargo
    parcel = Parcel.objects.create(cargo=cargo, track_number="PENDING002")
    response = cargo_admin_client.post(
        f"/api/parcels/{parcel.id}/assign/",
        {"client_code": "C0000001"},
        format="json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_pending_parcel_not_visible_to_client(auth_client):
    parcel = Parcel.objects.create(
        cargo=auth_client.user.cargo, track_number="PENDING003"
    )
    response = auth_client.get("/api/parcels/")
    items = (
        response.data["results"]
        if isinstance(response.data, dict) and "results" in response.data
        else response.data
    )
    assert parcel.track_number not in [i["track_number"] for i in items]
