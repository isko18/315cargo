"""Скан посылки, приехавшей из Китая, обязан присваивать клиента.

Жалоба админа: «сканируешь товар, который приехал из Китая, — код клиента не
спрашивает и не присваивается». Причина была в scan_parcel: client_code
использовался только при СОЗДАНИИ посылки. Посылка, принятая на складе в Китае
без клиента, при приёмке в ПВЗ уже существует — и введённый код молча
выбрасывался, а ответ «updated» выглядел как успех. По проду за неделю так
прошло 154 посылки, в ПВЗ без клиента лежало 340.
"""

import pytest

from notifications.models import Notification
from orders.models import Order
from parcels.models import Parcel
from tests.factories import UserFactory

SCAN = "/api/parcels/scan/"


@pytest.fixture
def client_user(db, cargo_admin):
    return UserFactory(
        cargo=cargo_admin.cargo,
        pickup_point=cargo_admin.pickup_point,
        client_code="KG-0001",
    )


def _from_china(cargo, track="CN-1", status=Parcel.Status.CUSTOMS):
    """Посылка, принятая на складе в Китае без клиента и доехавшая до КР."""
    return Parcel.objects.create(cargo=cargo, track_number=track, status=status)


def _parcel_notes(user, track):
    return [
        n for n in Notification.objects.filter(user=user)
        if (n.data or {}).get("track_number") == track
    ]


# --- присвоение по введённому коду ---


@pytest.mark.django_db
def test_code_is_assigned_to_parcel_arrived_from_china(cargo_admin_client, client_user):
    parcel = _from_china(cargo_admin_client.user.cargo)

    r = cargo_admin_client.post(
        SCAN,
        {"track_number": "CN-1", "client_code": "KG-0001", "status": "at_pickup_point"},
        format="json",
    )
    assert r.status_code == 200, r.data
    assert r.data["result"] == "updated"

    parcel.refresh_from_db()
    assert parcel.user_id == client_user.id
    assert parcel.client_code == "KG-0001"
    assert parcel.status == Parcel.Status.AT_PICKUP_POINT


@pytest.mark.django_db
def test_client_is_notified_that_parcel_is_at_pickup(cargo_admin_client, client_user):
    """Хозяина ставим ДО смены статуса: иначе «Посылка в ПВЗ» ушла бы в пустоту."""
    _from_china(cargo_admin_client.user.cargo)
    Notification.objects.filter(user=client_user).delete()

    cargo_admin_client.post(
        SCAN,
        {"track_number": "CN-1", "client_code": "KG-0001", "status": "at_pickup_point"},
        format="json",
    )

    notes = _parcel_notes(client_user, "CN-1")
    assert len(notes) == 1
    assert notes[0].data["status"] == Parcel.Status.AT_PICKUP_POINT


@pytest.mark.django_db
def test_rescan_to_add_code_assigns_and_is_not_unchanged(cargo_admin_client, client_user):
    """Самый частый случай: посылку уже приняли в ПВЗ без кода, сканируют снова с кодом.

    Статус тот же, но клиент присвоен — это изменение. «unchanged» здесь
    соврал бы: приложение показало бы «ничего не изменилось».
    """
    parcel = _from_china(cargo_admin_client.user.cargo, status=Parcel.Status.AT_PICKUP_POINT)
    Notification.objects.filter(user=client_user).delete()

    r = cargo_admin_client.post(
        SCAN,
        {"track_number": "CN-1", "client_code": "KG-0001", "status": "at_pickup_point"},
        format="json",
    )
    assert r.status_code == 200, r.data
    assert r.data["result"] == "updated"

    parcel.refresh_from_db()
    assert parcel.user_id == client_user.id
    # Статус не менялся, но клиент о посылке ещё не знал — уведомляем.
    assert len(_parcel_notes(client_user, "CN-1")) == 1


@pytest.mark.django_db
def test_unknown_code_changes_nothing(cargo_admin_client):
    """Опечатка в коде не должна полуприменить скан: ни статус, ни хозяин."""
    parcel = _from_china(cargo_admin_client.user.cargo)

    r = cargo_admin_client.post(
        SCAN,
        {"track_number": "CN-1", "client_code": "НЕТ-ТАКОГО", "status": "at_pickup_point"},
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "no_client"

    parcel.refresh_from_db()
    assert parcel.user_id is None
    assert parcel.status == Parcel.Status.CUSTOMS


@pytest.mark.django_db
def test_code_from_another_cargo_is_not_found(cargo_admin_client):
    from tests.factories import CargoCompanyFactory

    UserFactory(cargo=CargoCompanyFactory(), client_code="FOREIGN-1")
    parcel = _from_china(cargo_admin_client.user.cargo)

    r = cargo_admin_client.post(
        SCAN,
        {"track_number": "CN-1", "client_code": "FOREIGN-1", "status": "at_pickup_point"},
        format="json",
    )
    assert r.status_code == 400
    parcel.refresh_from_db()
    assert parcel.user_id is None


# --- посылку с хозяином не переписываем ---


@pytest.mark.django_db
def test_different_code_on_owned_parcel_is_a_conflict(cargo_admin_client, client_user):
    """Другой код на чужой посылке — это перепутанная коробка, а не повод сменить хозяина."""
    other = UserFactory(cargo=client_user.cargo, client_code="KG-0002")
    parcel = Parcel.objects.create(
        cargo=client_user.cargo, user=client_user, client_code="KG-0001",
        track_number="OWNED-1", status=Parcel.Status.CUSTOMS,
    )

    r = cargo_admin_client.post(
        SCAN,
        {"track_number": "OWNED-1", "client_code": "KG-0002", "status": "at_pickup_point"},
        format="json",
    )
    assert r.status_code == 409
    assert r.data["code"] == "client_mismatch"
    assert "KG-0001" in r.data["detail"]

    parcel.refresh_from_db()
    assert parcel.user_id == client_user.id
    assert parcel.status == Parcel.Status.CUSTOMS
    assert other.parcels.count() == 0


@pytest.mark.django_db
def test_same_code_on_owned_parcel_is_fine(cargo_admin_client, client_user):
    """Оператор по привычке вводит код и у своей посылки — это не ошибка."""
    Parcel.objects.create(
        cargo=client_user.cargo, user=client_user, client_code="KG-0001",
        track_number="OWNED-2", status=Parcel.Status.CUSTOMS,
    )
    r = cargo_admin_client.post(
        SCAN,
        {"track_number": "OWNED-2", "client_code": "KG-0001", "status": "at_pickup_point"},
        format="json",
    )
    assert r.status_code == 200, r.data
    assert r.data["result"] == "updated"


@pytest.mark.django_db
def test_rescan_owned_parcel_without_code_stays_unchanged(cargo_admin_client, client_user):
    """Контракт result не ломаем: повторный скан без изменений — unchanged."""
    Parcel.objects.create(
        cargo=client_user.cargo, user=client_user, client_code="KG-0001",
        track_number="OWNED-3", status=Parcel.Status.AT_PICKUP_POINT,
    )
    r = cargo_admin_client.post(
        SCAN, {"track_number": "OWNED-3", "status": "at_pickup_point"}, format="json"
    )
    assert r.data["result"] == "unchanged"


# --- без кода: подбираем по заказу ---


@pytest.mark.django_db
def test_order_is_matched_on_rescan_without_code(cargo_admin_client, client_user):
    """Заказ мог прийти уже после скана в Китае — при приёмке в ПВЗ подбираем по нему."""
    order = Order.objects.create(
        user=client_user, source=Order.Source.MANUAL, track_number="CN-ORD-1"
    )
    parcel = _from_china(cargo_admin_client.user.cargo, track="CN-ORD-1")

    r = cargo_admin_client.post(
        SCAN, {"track_number": "CN-ORD-1", "status": "at_pickup_point"}, format="json"
    )
    assert r.status_code == 200, r.data

    parcel.refresh_from_db()
    assert parcel.user_id == client_user.id
    assert parcel.order_id == order.id


# --- сигнал для интерфейса: просить код ---


@pytest.mark.django_db
def test_response_says_client_is_still_needed(cargo_admin_client):
    """Приложение спрашивало код только на created_pending и пропускало повторный скан.

    needs_client не зависит от result: интерфейс смотрит на него и просит код
    всегда, когда посылка осталась без хозяина.
    """
    _from_china(cargo_admin_client.user.cargo)

    r = cargo_admin_client.post(
        SCAN, {"track_number": "CN-1", "status": "at_pickup_point"}, format="json"
    )
    assert r.data["result"] == "updated"
    assert r.data["needs_client"] is True


@pytest.mark.django_db
def test_response_clears_flag_once_assigned(cargo_admin_client, client_user):
    _from_china(cargo_admin_client.user.cargo)

    r = cargo_admin_client.post(
        SCAN,
        {"track_number": "CN-1", "client_code": "KG-0001", "status": "at_pickup_point"},
        format="json",
    )
    assert r.data["needs_client"] is False


@pytest.mark.django_db
def test_new_pending_parcel_also_sets_flag(cargo_admin_client):
    r = cargo_admin_client.post(
        SCAN, {"track_number": "BRAND-NEW-1", "status": "at_pickup_point"}, format="json"
    )
    assert r.data["result"] == "created_pending"
    assert r.data["needs_client"] is True


# --- привязка вручную из панели (/assign/) ---


@pytest.mark.django_db
def test_manual_assign_notifies_client(cargo_admin_client, client_user):
    """Веб-панель привязывает клиента отдельным вызовом /assign/.

    Статус при этом не меняется, сигнал смены статуса не срабатывает — и клиент,
    чья посылка уже лежит в ПВЗ, так и не узнавал, что его ждут.
    """
    parcel = _from_china(cargo_admin_client.user.cargo, status=Parcel.Status.AT_PICKUP_POINT)
    Notification.objects.filter(user=client_user).delete()

    r = cargo_admin_client.post(
        f"/api/parcels/{parcel.id}/assign/", {"client_code": "KG-0001"}, format="json"
    )
    assert r.status_code == 200, r.data

    notes = _parcel_notes(client_user, "CN-1")
    assert len(notes) == 1
    assert notes[0].data["status"] == Parcel.Status.AT_PICKUP_POINT
