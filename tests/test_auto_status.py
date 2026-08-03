from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from notifications.models import Notification
from parcels.models import Parcel, ParcelStatusHistory
from parcels.services import advance_parcel_auto, update_parcel_status
from tests.factories import ParcelFactory, PickupPointFactory, UserFactory


def _anchor_china(parcel, when):
    """Перевести в 'на складе в Китае' и сдвинуть время начала цепочки в прошлое."""
    update_parcel_status(parcel, Parcel.Status.ARRIVED_CHINA_WAREHOUSE)
    ParcelStatusHistory.objects.filter(
        parcel=parcel, status=Parcel.Status.ARRIVED_CHINA_WAREHOUSE
    ).update(created_at=when)


@pytest.mark.django_db
def test_auto_flow_catches_up_to_processing():
    client = UserFactory()
    parcel = ParcelFactory(user=client, cargo=client.cargo)
    _anchor_china(parcel, timezone.now() - timedelta(days=30))

    assert advance_parcel_auto(parcel) is True
    parcel.refresh_from_db()
    # Прошло много времени → дошёл до последнего авто-статуса (ждёт скан в ПВЗ).
    assert parcel.status == Parcel.Status.PROCESSING
    # По каждому промежуточному шагу есть запись в истории (трекинг).
    statuses = set(
        ParcelStatusHistory.objects.filter(parcel=parcel).values_list("status", flat=True)
    )
    assert {
        Parcel.Status.IN_STORAGE,
        Parcel.Status.SENT_TO_KYRGYZSTAN,
        Parcel.Status.IN_TRANSIT,
        Parcel.Status.ARRIVED_KYRGYZSTAN,
        Parcel.Status.PROCESSING,
    } <= statuses


@pytest.mark.django_db
def test_auto_flow_partial_advance():
    parcel = ParcelFactory(status=Parcel.Status.CREATED)
    # Прошло 15 минут — только первый порог (10 мин) пройден.
    _anchor_china(parcel, timezone.now() - timedelta(minutes=15))

    assert advance_parcel_auto(parcel) is True
    parcel.refresh_from_db()
    assert parcel.status == Parcel.Status.IN_STORAGE


@pytest.mark.django_db
def test_auto_flow_stops_and_waits_for_pickup_scan():
    parcel = ParcelFactory(status=Parcel.Status.PROCESSING)
    # На последнем авто-статусе движок не двигает — ждёт ручной скан в ПВЗ.
    assert advance_parcel_auto(parcel) is False


@pytest.mark.django_db
def test_issued_archives_parcel():
    parcel = ParcelFactory(status=Parcel.Status.AT_PICKUP_POINT)
    update_parcel_status(parcel, Parcel.Status.ISSUED)
    parcel.refresh_from_db()
    assert parcel.status == Parcel.Status.ISSUED
    assert parcel.is_archived is True


@pytest.mark.django_db
def test_notify_pickup_ready_command():
    pp = PickupPointFactory(address="Бишкек, Павлова 13/4")
    client = UserFactory(cargo=pp.cargo, pickup_point=pp)
    ParcelFactory(user=client, cargo=pp.cargo, status=Parcel.Status.AT_PICKUP_POINT)
    # Посылка без клиента — напоминать некому.
    Parcel.objects.create(
        cargo=pp.cargo, track_number="NOUSER-1", status=Parcel.Status.AT_PICKUP_POINT
    )

    before = Notification.objects.filter(user=client).count()
    call_command("notify_pickup_ready")
    after = Notification.objects.filter(user=client).count()
    assert after == before + 1


@pytest.mark.django_db
def test_advance_command_runs():
    client = UserFactory()
    parcel = ParcelFactory(user=client, cargo=client.cargo)
    _anchor_china(parcel, timezone.now() - timedelta(days=30))
    call_command("advance_parcels")
    parcel.refresh_from_db()
    assert parcel.status == Parcel.Status.PROCESSING
