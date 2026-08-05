from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from notifications.models import Notification
from notifications.services import get_or_create_preference
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
    assert parcel.status == Parcel.Status.ARRIVED_KYRGYZSTAN
    # По каждому промежуточному шагу есть запись в истории (трекинг).
    statuses = set(
        ParcelStatusHistory.objects.filter(parcel=parcel).values_list("status", flat=True)
    )
    assert {
        Parcel.Status.PROCESSING,
        Parcel.Status.ARRIVED_TOPA,
        Parcel.Status.IN_TRANSIT,
        Parcel.Status.ARRIVED_KYRGYZSTAN,
    } <= statuses


@pytest.mark.django_db
def test_auto_flow_partial_advance():
    parcel = ParcelFactory(status=Parcel.Status.CREATED)
    # Прошёл 1 час — только первый порог (10 сек, Китай→обработка) пройден,
    # следующий (обработка→Топа, 4 дня) — ещё нет.
    _anchor_china(parcel, timezone.now() - timedelta(hours=1))

    assert advance_parcel_auto(parcel) is True
    parcel.refresh_from_db()
    assert parcel.status == Parcel.Status.PROCESSING


@pytest.mark.django_db
def test_auto_flow_stops_and_waits_for_pickup_scan():
    parcel = ParcelFactory(status=Parcel.Status.ARRIVED_KYRGYZSTAN)
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
def test_auto_step_notifies_client_once():
    """Один сдвиг — одно уведомление, с понятным текстом статуса."""
    client = UserFactory()
    parcel = ParcelFactory(user=client, cargo=client.cargo)
    _anchor_china(parcel, timezone.now() - timedelta(hours=1))
    Notification.objects.filter(user=client).delete()

    assert advance_parcel_auto(parcel) is True

    notes = list(Notification.objects.filter(user=client))
    assert len(notes) == 1
    assert notes[0].title == "Посылка на обработке"
    assert parcel.track_number in notes[0].body
    assert notes[0].data["status"] == Parcel.Status.PROCESSING
    assert notes[0].data["parcel_id"] == parcel.id


@pytest.mark.django_db
def test_catch_up_sends_single_notification_for_final_status():
    """Догон нескольких шагов не спамит: один пуш по итоговому статусу."""
    client = UserFactory()
    parcel = ParcelFactory(user=client, cargo=client.cargo)
    _anchor_china(parcel, timezone.now() - timedelta(days=30))
    Notification.objects.filter(user=client).delete()

    assert advance_parcel_auto(parcel) is True

    notes = list(Notification.objects.filter(user=client))
    assert len(notes) == 1
    assert notes[0].data["status"] == Parcel.Status.ARRIVED_KYRGYZSTAN
    assert notes[0].title == "Посылка прибыла в Кыргызстан"
    # Промежуточные шаги остались в истории — трекинг не потерян.
    statuses = set(
        ParcelStatusHistory.objects.filter(parcel=parcel).values_list("status", flat=True)
    )
    assert {Parcel.Status.PROCESSING, Parcel.Status.ARRIVED_TOPA} <= statuses


@pytest.mark.django_db
def test_parcel_without_client_is_not_notified():
    """«Ничья» посылка со склада в Китае: уведомлять некого, падать нельзя."""
    pp = PickupPointFactory()
    parcel = Parcel.objects.create(cargo=pp.cargo, track_number="NOUSER-AUTO")
    _anchor_china(parcel, timezone.now() - timedelta(days=30))
    before = Notification.objects.count()

    assert advance_parcel_auto(parcel) is True

    assert Notification.objects.count() == before


@pytest.mark.django_db
def test_client_can_mute_parcel_notifications():
    client = UserFactory()
    prefs = get_or_create_preference(client)
    prefs.parcel_status_enabled = False
    prefs.save()

    parcel = ParcelFactory(user=client, cargo=client.cargo)
    _anchor_china(parcel, timezone.now() - timedelta(hours=1))
    Notification.objects.filter(user=client).delete()

    assert advance_parcel_auto(parcel) is True
    assert Notification.objects.filter(user=client).count() == 0


@pytest.mark.django_db
def test_advance_command_runs():
    client = UserFactory()
    parcel = ParcelFactory(user=client, cargo=client.cargo)
    _anchor_china(parcel, timezone.now() - timedelta(days=30))
    call_command("advance_parcels")
    parcel.refresh_from_db()
    assert parcel.status == Parcel.Status.ARRIVED_KYRGYZSTAN
