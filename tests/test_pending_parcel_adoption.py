"""«Ничья» посылка должна находить хозяина, когда заказ доедет позже скана.

Оператор на складе в Китае сканирует коробку раньше, чем заказ успевает
синхронизироваться с маркетплейса: по проду в 454 случаях из 467 заказ появлялся
уже ПОСЛЕ скана, в среднем через 110 часов. На момент скана заказа ещё нет,
поэтому scan/ честно оставляет посылку ничьей (created_pending) — и раньше
никто её потом не подбирал.

Из этого росли сразу три жалобы карго: код клиента «не присваивается»,
уведомления «не приходят» (получателя нет) и клиент «не видит товар по треку»
(в его списке посылки нет).
"""

import pytest

from notifications.models import Notification
from orders.models import Order
from parcels.models import Parcel
from tests.factories import UserFactory

INGEST = "/api/integrations/pinduoduo/ingest/"


def _pending_parcel(track, cargo=None, status=Parcel.Status.ARRIVED_CHINA_WAREHOUSE):
    """Посылка со сканера: карго есть, клиента и заказа нет."""
    return Parcel.objects.create(
        cargo=cargo, track_number=track, status=status, user=None, order=None
    )


# --- присвоение ---


@pytest.mark.django_db
def test_order_adopts_pending_parcel_scanned_earlier(auth_client):
    user = auth_client.user
    parcel = _pending_parcel("ADOPT-1", cargo=user.cargo)

    r = auth_client.post(
        INGEST,
        {"orders": [{"external_order_id": "O-1", "track_number": "ADOPT-1",
                     "product_title": "Куртка", "status": "shipped"}]},
        format="json",
    )
    assert r.status_code == 200, r.data

    parcel.refresh_from_db()
    assert parcel.user_id == user.id
    assert parcel.order.external_order_id == "O-1"
    assert parcel.client_code == user.client_code
    assert parcel.cargo_id == user.cargo_id


@pytest.mark.django_db
def test_adoption_does_not_create_a_second_parcel(auth_client):
    """Вторая посылка на тот же трек — это и есть жалоба «товар дублируется»."""
    user = auth_client.user
    _pending_parcel("ADOPT-2", cargo=user.cargo)

    auth_client.post(
        INGEST,
        {"orders": [{"external_order_id": "O-2", "track_number": "ADOPT-2"}]},
        format="json",
    )
    assert Parcel.objects.filter(track_number="ADOPT-2").count() == 1


@pytest.mark.django_db
def test_adoption_notifies_client_about_current_status(auth_client):
    """Клиент узнаёт о посылке, которая уже лежит в ПВЗ.

    Пока посылка была ничьей, уведомлять было некого — ровно поэтому карго и
    жаловалось, что уведомления не приходят.
    """
    user = auth_client.user
    _pending_parcel("ADOPT-3", cargo=user.cargo, status=Parcel.Status.AT_PICKUP_POINT)
    Notification.objects.filter(user=user).delete()

    auth_client.post(
        INGEST,
        {"orders": [{"external_order_id": "O-3", "track_number": "ADOPT-3"}]},
        format="json",
    )

    # Синхронизация заказа уведомляет ещё и о самом заказе, поэтому ищем
    # именно уведомление о посылке, а не единственное в списке.
    about_parcel = [
        n for n in Notification.objects.filter(user=user)
        if (n.data or {}).get("track_number") == "ADOPT-3"
    ]
    assert len(about_parcel) == 1, list(Notification.objects.filter(user=user))
    assert about_parcel[0].data["status"] == Parcel.Status.AT_PICKUP_POINT


@pytest.mark.django_db
def test_client_sees_adopted_parcel_in_own_list(auth_client):
    """Жалоба «клиент не видит товар по трек-номеру» — следствие ничьей посылки."""
    user = auth_client.user
    _pending_parcel("ADOPT-4", cargo=user.cargo)

    before = auth_client.get("/api/parcels/?track_number=ADOPT-4")
    rows = before.data["results"] if isinstance(before.data, dict) else before.data
    assert rows == []

    auth_client.post(
        INGEST,
        {"orders": [{"external_order_id": "O-4", "track_number": "ADOPT-4"}]},
        format="json",
    )

    after = auth_client.get("/api/parcels/?track_number=ADOPT-4")
    rows = after.data["results"] if isinstance(after.data, dict) else after.data
    assert [p["track_number"] for p in rows] == ["ADOPT-4"]


# --- границы: чужое не присваиваем ---


@pytest.mark.django_db
def test_parcel_of_another_client_is_never_stolen(auth_client):
    """Посылка с хозяином остаётся у него, даже если трек совпал."""
    owner = UserFactory(cargo=auth_client.user.cargo)
    parcel = Parcel.objects.create(
        cargo=owner.cargo, user=owner, client_code=owner.client_code,
        track_number="OWNED-1", status=Parcel.Status.ARRIVED_CHINA_WAREHOUSE,
    )

    r = auth_client.post(
        INGEST,
        {"orders": [{"external_order_id": "O-5", "track_number": "OWNED-1"}]},
        format="json",
    )
    assert r.status_code == 200, r.data

    parcel.refresh_from_db()
    assert parcel.user_id == owner.id
    assert parcel.order_id is None


@pytest.mark.django_db
def test_parcel_already_linked_to_another_order_is_not_touched(auth_client):
    user = auth_client.user
    other_order = Order.objects.create(user=user, source=Order.Source.MANUAL)
    parcel = Parcel.objects.create(
        cargo=user.cargo, user=user, order=other_order,
        track_number="LINKED-1", status=Parcel.Status.ARRIVED_CHINA_WAREHOUSE,
    )

    auth_client.post(
        INGEST,
        {"orders": [{"external_order_id": "O-6", "track_number": "LINKED-1"}]},
        format="json",
    )

    parcel.refresh_from_db()
    assert parcel.order_id == other_order.id


# --- разовая подтяжка накопленного ---


@pytest.mark.django_db
def test_relink_command_attaches_existing_pending_parcels():
    """На проде 467 таких посылок уже накопилось — их надо подобрать разом."""
    from django.core.management import call_command

    user = UserFactory()
    order = Order.objects.create(
        user=user, source=Order.Source.MANUAL, track_number="OLD-1"
    )
    parcel = _pending_parcel("OLD-1", cargo=user.cargo)

    call_command("relink_pending_parcels", "--apply")

    parcel.refresh_from_db()
    assert parcel.user_id == user.id
    assert parcel.order_id == order.id
    assert parcel.client_code == user.client_code


@pytest.mark.django_db
def test_relink_dry_run_changes_nothing():
    from django.core.management import call_command

    user = UserFactory()
    Order.objects.create(user=user, source=Order.Source.MANUAL, track_number="OLD-2")
    parcel = _pending_parcel("OLD-2", cargo=user.cargo)

    call_command("relink_pending_parcels")

    parcel.refresh_from_db()
    assert parcel.user_id is None


@pytest.mark.django_db
def test_relink_is_silent_by_default():
    """Подтяжка — это починка данных, а не движение коробки: пуши не шлём.

    467 уведомлений разом клиенты прочитали бы как сбой.
    """
    from django.core.management import call_command

    user = UserFactory()
    Order.objects.create(user=user, source=Order.Source.MANUAL, track_number="OLD-3")
    _pending_parcel("OLD-3", cargo=user.cargo, status=Parcel.Status.AT_PICKUP_POINT)
    Notification.objects.filter(user=user).delete()

    call_command("relink_pending_parcels", "--apply")

    assert Notification.objects.filter(user=user).count() == 0


@pytest.mark.django_db
def test_relink_can_notify_on_demand():
    from django.core.management import call_command

    user = UserFactory()
    Order.objects.create(user=user, source=Order.Source.MANUAL, track_number="OLD-4")
    _pending_parcel("OLD-4", cargo=user.cargo, status=Parcel.Status.AT_PICKUP_POINT)
    Notification.objects.filter(user=user).delete()

    call_command("relink_pending_parcels", "--apply", "--notify")

    assert Notification.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_relink_skips_parcels_without_matching_order():
    from django.core.management import call_command

    user = UserFactory()
    parcel = _pending_parcel("NOORDER-1", cargo=user.cargo)

    call_command("relink_pending_parcels", "--apply")

    parcel.refresh_from_db()
    assert parcel.user_id is None


# --- контракт scan/: значения result (на них завязан интерфейс) ---


@pytest.mark.django_db
def test_scan_result_values_are_a_contract(cargo_admin_client):
    """Мобильное приложение различает приём и повтор по полю result.

    Просьба команды: не убирать поле и не менять значения. Тест это фиксирует.
    """
    client = UserFactory(cargo=cargo_admin_client.user.cargo, client_code="RES-0001")

    first = cargo_admin_client.post(
        "/api/parcels/scan/",
        {"track_number": "RESULT-1", "client_code": "RES-0001",
         "status": "at_pickup_point"},
        format="json",
    )
    assert first.status_code == 201, first.data
    assert first.data["result"] == "created_manual"

    same = cargo_admin_client.post(
        "/api/parcels/scan/",
        {"track_number": "RESULT-1", "client_code": "RES-0001",
         "status": "at_pickup_point"},
        format="json",
    )
    assert same.data["result"] == "unchanged"

    pending = cargo_admin_client.post(
        "/api/parcels/scan/",
        {"track_number": "RESULT-2", "status": "arrived_china_warehouse"},
        format="json",
    )
    assert pending.data["result"] == "created_pending"
    # Поля посылки лежат во вложенном parcel, а не в корне ответа.
    assert pending.data["parcel"]["user"] is None

    moved = cargo_admin_client.post(
        "/api/parcels/scan/",
        {"track_number": "RESULT-2", "status": "at_pickup_point"},
        format="json",
    )
    assert moved.data["result"] == "updated"
    assert client.client_code == "RES-0001"


@pytest.mark.django_db
def test_scan_without_status_defaults_to_china_warehouse(cargo_admin_client):
    """status в scan/ необязателен — об этом просили в прошлом документе."""
    r = cargo_admin_client.post(
        "/api/parcels/scan/", {"track_number": "NOSTATUS-1"}, format="json"
    )
    assert r.status_code == 201, r.data
    assert Parcel.objects.get(track_number="NOSTATUS-1").status == (
        Parcel.Status.ARRIVED_CHINA_WAREHOUSE
    )
