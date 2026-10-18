"""Сортировка в ПВЗ: молчаливый статус перед «Прибыл в пункт выдачи».

Карго жаловалось: «можете забрать» уходило в момент разгрузки машины, и
клиенты приходили к закрытой двери или к неразобранной куче. Теперь приёмка
ставит sorting — клиенту тихо, — а «Готов к выдаче» переводит в
at_pickup_point, и только это звенит.

Главное, что держат тесты: в сортировке нет пуша ни одним путём (скан,
«ничья» посылка нашла хозяина), скан sorting не считается откатом, а выход
из сортировки уведомляет каждого клиента по его посылкам.
"""

import pytest

from notifications.models import Notification, NotificationType
from parcels.models import Parcel, ParcelStatusHistory
from tests.factories import PickupPointFactory, UserFactory

SORTING = Parcel.Status.SORTING
AT_PVZ = Parcel.Status.AT_PICKUP_POINT


@pytest.fixture
def client_user(cargo_admin):
    return UserFactory(cargo=cargo_admin.cargo)


def _parcel(user, status, track):
    return Parcel.objects.create(
        cargo=user.cargo, user=user, client_code=user.client_code,
        track_number=track, status=status,
    )


def _notes(user):
    return Notification.objects.filter(user=user).count()


def _scan(api, track, status, **extra):
    return api.post(
        "/api/parcels/scan/", {"track_number": track, "status": status, **extra}, format="json"
    )


# --- Молчание ---


@pytest.mark.django_db
@pytest.mark.parametrize(
    "before", ["customs", "arrived_kyrgyzstan", "arrived_topa", "in_transit"]
)
def test_scan_to_sorting_moves_forward_silently(cargo_admin_client, client_user, before):
    """Из любого более раннего статуса — вперёд, не 409, и без пуша."""
    _parcel(client_user, before, "SRT-1")
    notes = _notes(client_user)

    r = _scan(cargo_admin_client, "SRT-1", "sorting")

    assert r.status_code in (200, 201), r.data
    assert Parcel.objects.get(track_number="SRT-1").status == SORTING
    assert _notes(client_user) == notes


@pytest.mark.django_db
def test_sorting_step_is_visible_in_history(cargo_admin_client, client_user):
    """Карго должно видеть, когда коробку разобрали — даже без пуша."""
    parcel = _parcel(client_user, "customs", "SRT-H")

    _scan(cargo_admin_client, "SRT-H", "sorting")

    assert ParcelStatusHistory.objects.filter(parcel=parcel, status=SORTING).exists()
    r = cargo_admin_client.get(f"/api/parcels/{parcel.id}/history/")
    assert SORTING in [row["status"] for row in r.data]


@pytest.mark.django_db
def test_sorting_scan_stamps_the_pickup_point(cargo_admin_client, client_user):
    """Коробка уже на полке ПВЗ: без пункта она пропала бы из его склада."""
    point = PickupPointFactory(cargo=client_user.cargo)
    _parcel(client_user, "customs", "SRT-P")

    _scan(cargo_admin_client, "SRT-P", "sorting", pickup_point=point.id)

    assert Parcel.objects.get(track_number="SRT-P").pickup_point_id == point.id


@pytest.mark.django_db
def test_new_parcel_scanned_straight_into_sorting_is_silent(cargo_admin_client, client_user):
    """Коробка без предварительной записи — тоже без пуша."""
    notes = _notes(client_user)

    r = _scan(
        cargo_admin_client, "SRT-NEW", "sorting", client_code=client_user.client_code
    )

    assert r.status_code in (200, 201), r.data
    assert _notes(client_user) == notes


@pytest.mark.django_db
def test_orphan_in_sorting_finding_its_owner_stays_silent(client_user):
    """Второй путь к пушу — «ничья» посылка нашла хозяина. Тоже молчит."""
    from parcels.signals import send_parcel_status_notification

    parcel = _parcel(client_user, SORTING, "SRT-ORPH")
    notes = _notes(client_user)

    assert send_parcel_status_notification(parcel) is False
    assert _notes(client_user) == notes


@pytest.mark.django_db
def test_sorting_does_not_stamp_notified_at(cargo_admin_client, client_user):
    parcel = _parcel(client_user, "customs", "SRT-N")
    parcel.refresh_from_db()
    before = parcel.notified_at

    _scan(cargo_admin_client, "SRT-N", "sorting")

    parcel.refresh_from_db()
    assert parcel.notified_at == before


# --- Выход из сортировки ---


@pytest.mark.django_db
def test_sorting_to_pickup_by_scan_notifies(cargo_admin_client, client_user):
    _parcel(client_user, SORTING, "SRT-S")

    r = _scan(cargo_admin_client, "SRT-S", "at_pickup_point")

    assert r.status_code == 200, r.data
    assert Notification.objects.filter(
        user=client_user, type=NotificationType.PARCEL_AT_PICKUP_POINT
    ).count() == 1


@pytest.mark.django_db
def test_ready_button_notifies_every_client_for_every_parcel(cargo_admin_client, cargo_admin):
    """«Готов к выдаче» = bulk-status. Не одно на всех и не ни одного."""
    cargo = cargo_admin.cargo
    anna, boris = UserFactory(cargo=cargo), UserFactory(cargo=cargo)
    parcels = [
        _parcel(anna, SORTING, "SRT-A1"),
        _parcel(anna, SORTING, "SRT-A2"),
        _parcel(boris, SORTING, "SRT-B1"),
    ]

    r = cargo_admin_client.post(
        "/api/manage/parcels/bulk-status/",
        {"ids": [p.id for p in parcels], "status": "at_pickup_point"},
        format="json",
    )

    assert r.data["updated"] == 3
    ready = Notification.objects.filter(type=NotificationType.PARCEL_AT_PICKUP_POINT)
    assert ready.filter(user=anna).count() == 2
    assert ready.filter(user=boris).count() == 1


@pytest.mark.django_db
def test_rescanning_at_pickup_back_to_sorting_is_rejected(cargo_admin_client, client_user):
    """Сканер не откатывает: «Готов» нажат — повторный скан sorting не пройдёт."""
    _parcel(client_user, AT_PVZ, "SRT-BACK")

    r = _scan(cargo_admin_client, "SRT-BACK", "sorting")

    assert r.status_code == 409
    assert r.data["code"] == "already_advanced"


@pytest.mark.django_db
def test_panel_can_return_parcel_to_sorting(cargo_admin_client, client_user):
    """Нажали «Готов» раньше времени — панель вернёт, и это снова тихо."""
    parcel = _parcel(client_user, AT_PVZ, "SRT-UNDO")
    notes = _notes(client_user)

    r = cargo_admin_client.post(
        "/api/manage/parcels/bulk-status/",
        {"ids": [parcel.id], "status": "sorting"},
        format="json",
    )

    assert r.data["updated"] == 1
    assert _notes(client_user) == notes


# --- Остальное ---


@pytest.mark.django_db
def test_filter_by_sorting(cargo_admin_client, client_user):
    _parcel(client_user, SORTING, "SRT-F1")
    _parcel(client_user, AT_PVZ, "SRT-F2")

    rows = cargo_admin_client.get("/api/parcels/?status=sorting").data

    assert [p["track_number"] for p in rows] == ["SRT-F1"]


@pytest.mark.django_db
def test_sorting_is_not_part_of_the_timed_chain(client_user):
    """Ставится только руками: часы его не двигают и в него не приводят."""
    from datetime import timedelta

    from django.utils import timezone

    from parcels.services import AUTO_FLOW, advance_parcel_auto

    parcel = _parcel(client_user, SORTING, "SRT-AUTO")

    assert SORTING not in AUTO_FLOW
    assert advance_parcel_auto(parcel, now=timezone.now() + timedelta(days=365)) is False


@pytest.mark.django_db
def test_china_operator_cannot_set_sorting(api_client, client_user):
    from rest_framework_simplejwt.tokens import RefreshToken

    from users.models import User

    op = User.objects.create(
        phone="+996700000778", is_staff=True, is_china_staff=True, cargo=None
    )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(op).access_token}")
    _parcel(client_user, "customs", "SRT-CN")

    r = _scan(api_client, "SRT-CN", "sorting")

    assert r.status_code == 403


@pytest.mark.django_db
def test_sorting_scan_shows_up_in_receive_history(cargo_admin_client, client_user):
    """Иначе принятые по-новому коробки пропадают из истории приёма оператора."""
    _parcel(client_user, "customs", "SRT-HIST")
    _scan(cargo_admin_client, "SRT-HIST", "sorting")

    rows = cargo_admin_client.get("/api/history/?type=receive&limit=50").data["results"]

    assert "SRT-HIST" in [r["track_number"] for r in rows]
