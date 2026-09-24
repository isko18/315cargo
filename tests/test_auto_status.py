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
    """Перевести на склад в Китае и сдвинуть время начала цепочки в прошлое."""
    update_parcel_status(parcel, Parcel.Status.ARRIVED_CHINA_WAREHOUSE)
    ParcelStatusHistory.objects.filter(
        parcel=parcel, status=Parcel.Status.ARRIVED_CHINA_WAREHOUSE
    ).update(created_at=when)


# --- Маршрут: склад в Китае → (1 день) В пути → (7 дней) На таможне → скан в ПВЗ ---


@pytest.mark.django_db
def test_auto_flow_catches_up_to_customs():
    client = UserFactory()
    parcel = ParcelFactory(user=client, cargo=client.cargo)
    _anchor_china(parcel, timezone.now() - timedelta(days=30))

    assert advance_parcel_auto(parcel) is True
    parcel.refresh_from_db()
    # Прошло много времени → дошёл до последнего авто-статуса (ждёт скан в ПВЗ).
    assert parcel.status == Parcel.Status.CUSTOMS
    # Промежуточный шаг остался в истории — трекинг не потерян.
    statuses = set(
        ParcelStatusHistory.objects.filter(parcel=parcel).values_list("status", flat=True)
    )
    assert {Parcel.Status.IN_TRANSIT, Parcel.Status.CUSTOMS} <= statuses


@pytest.mark.django_db
@pytest.mark.parametrize(
    "age,expected",
    [
        (timedelta(hours=2), Parcel.Status.ARRIVED_CHINA_WAREHOUSE),
        (timedelta(days=1, hours=1), Parcel.Status.IN_TRANSIT),
        (timedelta(days=7, hours=23), Parcel.Status.IN_TRANSIT),
        (timedelta(days=8, hours=1), Parcel.Status.CUSTOMS),
        (timedelta(days=60), Parcel.Status.CUSTOMS),
    ],
)
def test_timeline_one_day_transit_then_seven(age, expected):
    """Согласованный маршрут: +1 день → В пути, +7 дней → На таможне (итого 8)."""
    client = UserFactory()
    parcel = ParcelFactory(user=client, cargo=client.cargo)
    _anchor_china(parcel, timezone.now() - age)

    advance_parcel_auto(parcel)
    parcel.refresh_from_db()
    assert parcel.status == expected


@pytest.mark.django_db
def test_first_day_on_china_warehouse_does_not_move():
    """Статус на складе в Китае обязан прожить сутки, а не 10 секунд."""
    parcel = ParcelFactory(status=Parcel.Status.CREATED)
    _anchor_china(parcel, timezone.now() - timedelta(hours=3))

    assert advance_parcel_auto(parcel) is False
    parcel.refresh_from_db()
    assert parcel.status == Parcel.Status.ARRIVED_CHINA_WAREHOUSE


@pytest.mark.django_db
def test_customs_waits_for_pickup_scan():
    """На таможне — последний авто-статус: дальше только реальный скан в ПВЗ."""
    parcel = ParcelFactory(status=Parcel.Status.CUSTOMS)
    assert advance_parcel_auto(parcel) is False


@pytest.mark.django_db
def test_processing_is_not_auto_step_anymore():
    """Классификация и обработка убрана из авто-цепочки."""
    from parcels.services import AUTO_FLOW

    assert Parcel.Status.PROCESSING not in AUTO_FLOW


@pytest.mark.django_db
def test_auto_chain_never_claims_arrival_in_kyrgyzstan():
    """Физическое прибытие таймером не объявляется — только сканом.

    Раньше цепочка сама ставила «Прибыл в Кыргызстан» на 9-й день, и клиент
    получал пуш о прибытии, пока фура ещё ехала.
    """
    from parcels.services import AUTO_FLOW

    assert Parcel.Status.ARRIVED_KYRGYZSTAN not in AUTO_FLOW
    assert Parcel.Status.AT_PICKUP_POINT not in AUTO_FLOW


@pytest.mark.django_db
def test_status_rank_matches_auto_flow():
    """Ранг защищает от отката при повторном скане.

    Если он разойдётся с AUTO_FLOW, авто-переход будет выглядеть откатом назад
    и повторный скан начнёт отклоняться с «посылка уже дальше по маршруту».
    """
    from parcels.services import AUTO_FLOW, STATUS_RANK

    ranks = [STATUS_RANK[s] for s in AUTO_FLOW]
    assert ranks == sorted(ranks)


@pytest.mark.django_db
def test_customs_rank_is_before_pickup_point():
    """Скан в ПВЗ после таможни обязан проходить, а не считаться откатом."""
    from parcels.services import STATUS_RANK

    assert STATUS_RANK[Parcel.Status.CUSTOMS] < STATUS_RANK[Parcel.Status.AT_PICKUP_POINT]


# --- Уведомления ---


@pytest.mark.django_db
def test_auto_step_notifies_client_once():
    """Один сдвиг — одно уведомление, с понятным текстом статуса."""
    client = UserFactory()
    parcel = ParcelFactory(user=client, cargo=client.cargo)
    _anchor_china(parcel, timezone.now() - timedelta(days=1, hours=1))
    Notification.objects.filter(user=client).delete()

    assert advance_parcel_auto(parcel) is True

    notes = list(Notification.objects.filter(user=client))
    assert len(notes) == 1
    assert notes[0].title == "Посылка в пути"
    assert parcel.track_number in notes[0].body
    assert notes[0].data["status"] == Parcel.Status.IN_TRANSIT
    assert notes[0].data["parcel_id"] == parcel.id


@pytest.mark.django_db
def test_customs_notification_has_own_text():
    client = UserFactory()
    parcel = ParcelFactory(user=client, cargo=client.cargo)
    _anchor_china(parcel, timezone.now() - timedelta(days=30))
    Notification.objects.filter(user=client).delete()

    assert advance_parcel_auto(parcel) is True

    notes = list(Notification.objects.filter(user=client))
    assert len(notes) == 1
    assert notes[0].data["status"] == Parcel.Status.CUSTOMS
    assert notes[0].title == "Посылка на таможне"


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
    assert notes[0].data["status"] == Parcel.Status.CUSTOMS
    # Промежуточный шаг остался в истории — трекинг не потерян.
    statuses = set(
        ParcelStatusHistory.objects.filter(parcel=parcel).values_list("status", flat=True)
    )
    assert Parcel.Status.IN_TRANSIT in statuses


@pytest.mark.django_db
def test_parcel_without_client_is_not_notified():
    """Ничья посылка со склада в Китае: уведомлять некого, падать нельзя."""
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
    _anchor_china(parcel, timezone.now() - timedelta(days=1, hours=1))
    Notification.objects.filter(user=client).delete()

    assert advance_parcel_auto(parcel) is True
    assert Notification.objects.filter(user=client).count() == 0


# --- Команды ---


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
    assert parcel.status == Parcel.Status.CUSTOMS


@pytest.mark.django_db
def test_catchup_moves_status_without_notifying():
    """Сдвиг вызван правкой настроек, а не движением коробки.

    Пуш здесь был бы ложным, а при сотнях посылок читался бы как сбой.
    Обычный крон уведомления шлёт — он реагирует на реальное время.
    """
    client = UserFactory()
    get_or_create_preference(client)
    parcel = ParcelFactory(user=client, cargo=client.cargo)
    _anchor_china(parcel, timezone.now() - timedelta(days=10))
    Notification.objects.filter(user=client).delete()

    call_command("catchup_auto_statuses", "--apply")

    parcel.refresh_from_db()
    assert parcel.status == Parcel.Status.CUSTOMS
    assert Notification.objects.filter(user=client).count() == 0


@pytest.mark.django_db
def test_catchup_dry_run_changes_nothing():
    client = UserFactory()
    parcel = ParcelFactory(user=client, cargo=client.cargo)
    _anchor_china(parcel, timezone.now() - timedelta(days=10))
    parcel.refresh_from_db()
    before = parcel.status

    call_command("catchup_auto_statuses")

    parcel.refresh_from_db()
    assert parcel.status == before


@pytest.mark.django_db
def test_regular_cron_still_notifies():
    """Глушение — только у подтяжки: обычный прогон обязан уведомлять."""
    client = UserFactory()
    get_or_create_preference(client)
    parcel = ParcelFactory(user=client, cargo=client.cargo)
    _anchor_china(parcel, timezone.now() - timedelta(days=10))
    Notification.objects.filter(user=client).delete()

    advance_parcel_auto(parcel)

    assert Notification.objects.filter(user=client).exists()


# --- Разовый перевод застрявших в обработке ---


@pytest.mark.django_db
def test_drain_processing_moves_to_transit_silently():
    """PROCESSING выпал из цепочки — накопленные посылки надо увести вручную.

    Без этого они остались бы в статусе, который больше никто не двигает.
    Пуш здесь был бы ложным: коробка никуда не поехала.
    """
    client = UserFactory()
    get_or_create_preference(client)
    parcel = ParcelFactory(user=client, cargo=client.cargo, status=Parcel.Status.PROCESSING)
    Notification.objects.filter(user=client).delete()

    call_command("drain_processing", "--apply")

    parcel.refresh_from_db()
    assert parcel.status == Parcel.Status.IN_TRANSIT
    assert Notification.objects.filter(user=client).count() == 0


@pytest.mark.django_db
def test_drain_processing_dry_run_changes_nothing():
    parcel = ParcelFactory(status=Parcel.Status.PROCESSING)

    call_command("drain_processing")

    parcel.refresh_from_db()
    assert parcel.status == Parcel.Status.PROCESSING
