import io

import pytest

from parcels.imports import import_parcels_from_csv
from parcels.models import Parcel, ParcelStatusHistory
from tests.factories import ParcelFactory


@pytest.mark.django_db
def test_parcels_list_filters_to_owner(auth_client):
    parcel = ParcelFactory(user=auth_client.user)
    ParcelFactory()  # another user's parcel
    response = auth_client.get("/api/parcels/")
    assert response.status_code == 200
    items = (
        response.data["results"]
        if isinstance(response.data, dict) and "results" in response.data
        else response.data
    )
    track_numbers = [item["track_number"] for item in items]
    assert parcel.track_number in track_numbers
    assert len(items) == 1


@pytest.mark.django_db
def test_parcel_history_records_status_change(auth_client):
    parcel = ParcelFactory(user=auth_client.user)
    parcel.status = Parcel.Status.AT_PICKUP_POINT
    parcel.save(update_fields=("status", "updated_at"))

    response = auth_client.get(f"/api/parcels/{parcel.id}/history/")
    assert response.status_code == 200
    statuses = [row["status"] for row in response.data]
    assert Parcel.Status.AT_PICKUP_POINT in statuses


@pytest.mark.django_db
def test_status_timestamps_set(auth_client):
    from parcels.services import update_parcel_status

    parcel = ParcelFactory(user=auth_client.user)
    assert parcel.arrived_at is None and parcel.issued_at is None

    update_parcel_status(parcel, Parcel.Status.ARRIVED_KYRGYZSTAN)
    parcel.refresh_from_db()
    assert parcel.arrived_at is not None
    arrived_at = parcel.arrived_at

    update_parcel_status(parcel, Parcel.Status.ISSUED)
    parcel.refresh_from_db()
    assert parcel.issued_at is not None
    # arrived_at is not overwritten on later transitions.
    assert parcel.arrived_at == arrived_at


@pytest.mark.django_db
def test_csv_import_rejects_owner_reassignment(user):
    from tests.factories import UserFactory

    other = UserFactory()
    ParcelFactory(user=user, track_number="DUP123")
    csv_content = (
        "track_number,client_code,status\n"
        f"DUP123,{other.client_code},purchased\n"
    ).encode("utf-8")
    result = import_parcels_from_csv(io.BytesIO(csv_content))
    assert result.updated == 0
    assert result.skipped == 1
    assert any("принадлежит другому" in err for err in result.errors)
    assert Parcel.objects.get(track_number="DUP123").user_id == user.id


@pytest.mark.django_db
def test_csv_import_creates_parcels(user):
    csv_content = (
        "track_number,client_code,status,location,weight\n"
        f"AAA111,{user.client_code},purchased,Guangzhou,2.5\n"
        f"BBB222,{user.client_code},sent_to_kyrgyzstan,,1.0\n"
    ).encode("utf-8")
    result = import_parcels_from_csv(io.BytesIO(csv_content))
    assert result.created == 2
    assert result.errors == []
    assert Parcel.objects.filter(track_number="AAA111", status="purchased").exists()


@pytest.mark.django_db
def test_csv_import_reports_unknown_client(user):
    csv_content = (
        "track_number,client_code,status\n"
        "XXX999,C9999999,purchased\n"
    ).encode("utf-8")
    result = import_parcels_from_csv(io.BytesIO(csv_content))
    assert result.created == 0
    assert result.skipped == 1
    assert any("не найден" in err for err in result.errors)
