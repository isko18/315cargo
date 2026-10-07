"""Одна физическая коробка — одна посылка у заказа.

Пока у заказа нет трека, синхронизация заводит посылку-заглушку с номером
заказа вместо трека. Физическую коробку тем временем сканируют на складе с
настоящим треком, и она остаётся ничьей. Раньше, когда подбиралась ничья
посылка, заглушку не учитывали — и у заказа становилось ДВЕ посылки: клиент
видел обе в ПВЗ, выдавали одну, а по второй бесконечно шли напоминания.

Именно так подбор 01.10 задвоил 10 заказов на проде. Правило теперь одно на все
пути (синхронизация заказа, скан, подтяжка): заглушка уступает место физической
посылке; настоящая посылка с другим треком — это конфликт, и тогда ничего не
привязываем, чтобы не плодить вторую.
"""

import pytest

from notifications.models import Notification
from orders.models import Order
from parcels.models import Parcel
from tests.factories import UserFactory

INGEST = "/api/integrations/pinduoduo/ingest/"
SCAN = "/api/parcels/scan/"


def _active(order):
    return Parcel.objects.filter(order=order, is_archived=False).exclude(
        status=Parcel.Status.CANCELLED
    )


@pytest.fixture
def owner(db, cargo_admin):
    return UserFactory(
        cargo=cargo_admin.cargo, pickup_point=cargo_admin.pickup_point,
        client_code="PH-0001",
    )


@pytest.fixture
def order(owner):
    return Order.objects.create(
        user=owner, source=Order.Source.PINDUODUO,
        external_order_id="EXT-1", track_number="REAL-1",
    )


def _placeholder(order, status=Parcel.Status.CREATED):
    """Заглушка: синхронизация завела её, пока у заказа не было трека."""
    return Parcel.objects.create(
        cargo=order.user.cargo, user=order.user, order=order,
        client_code=order.user.client_code, track_number=order.external_order_id,
        status=status,
    )


def _physical(cargo, track="REAL-1", status=Parcel.Status.CUSTOMS):
    """Настоящая коробка: отсканирована на складе в Китае, без клиента."""
    return Parcel.objects.create(cargo=cargo, track_number=track, status=status)


# --- скан ---


@pytest.mark.django_db
def test_scan_replaces_placeholder_with_physical_parcel(cargo_admin_client, order):
    placeholder = _placeholder(order)
    physical = _physical(order.user.cargo)

    r = cargo_admin_client.post(
        SCAN, {"track_number": "REAL-1", "status": "at_pickup_point"}, format="json"
    )
    assert r.status_code == 200, r.data
    assert r.data["needs_client"] is False

    physical.refresh_from_db()
    placeholder.refresh_from_db()
    assert physical.order_id == order.id
    assert physical.user_id == order.user_id
    assert placeholder.status == Parcel.Status.CANCELLED
    assert placeholder.is_archived is True
    assert list(_active(order)) == [physical]


@pytest.mark.django_db
def test_scan_leaves_parcel_alone_when_order_has_a_real_parcel(cargo_admin_client, order):
    """У заказа уже есть посылка с НАСТОЯЩИМ треком — это не заглушка.

    Привязать вторую значит задвоить заказ. Оставляем ничьей и просим код.
    """
    Parcel.objects.create(
        cargo=order.user.cargo, user=order.user, order=order,
        track_number="OTHER-REAL", status=Parcel.Status.CUSTOMS,
    )
    physical = _physical(order.user.cargo)

    r = cargo_admin_client.post(
        SCAN, {"track_number": "REAL-1", "status": "at_pickup_point"}, format="json"
    )
    assert r.status_code == 200, r.data
    assert r.data["needs_client"] is True

    physical.refresh_from_db()
    assert physical.user_id is None
    assert physical.order_id is None
    assert _active(order).count() == 1


@pytest.mark.django_db
def test_issued_placeholder_is_never_retired(cargo_admin_client, order):
    """Заглушку уже выдали клиенту — под ней ушла коробка. Не трогаем."""
    placeholder = _placeholder(order, status=Parcel.Status.ISSUED)
    physical = _physical(order.user.cargo)

    cargo_admin_client.post(
        SCAN, {"track_number": "REAL-1", "status": "at_pickup_point"}, format="json"
    )

    placeholder.refresh_from_db()
    physical.refresh_from_db()
    assert placeholder.status == Parcel.Status.ISSUED
    assert physical.order_id is None


@pytest.mark.django_db
def test_placeholder_retirement_is_silent(cargo_admin_client, order):
    """Пуш «посылка отменена» про заглушку напугал бы клиента зря."""
    _placeholder(order, status=Parcel.Status.AT_PICKUP_POINT)
    _physical(order.user.cargo)
    Notification.objects.filter(user=order.user).delete()

    cargo_admin_client.post(
        SCAN, {"track_number": "REAL-1", "status": "at_pickup_point"}, format="json"
    )

    cancelled = [
        n for n in Notification.objects.filter(user=order.user)
        if (n.data or {}).get("status") == Parcel.Status.CANCELLED
    ]
    assert cancelled == []


# --- синхронизация заказа ---


@pytest.mark.django_db
def test_sync_merges_when_real_track_arrives(auth_client):
    """Заглушка есть, коробку уже отсканировали, и тут с маркетплейса приходит трек.

    Раньше переименование заглушки в реальный трек молча пропускалось («трек
    занят»), и заказ оставался с заглушкой, а коробка — ничьей.
    """
    user = auth_client.user
    order = Order.objects.create(
        user=user, source=Order.Source.PINDUODUO, external_order_id="EXT-9",
    )
    placeholder = _placeholder(order)
    physical = _physical(user.cargo, track="REAL-9")

    r = auth_client.post(
        INGEST,
        {"orders": [{"external_order_id": "EXT-9", "track_number": "REAL-9",
                     "status": "shipped"}]},
        format="json",
    )
    assert r.status_code == 200, r.data

    physical.refresh_from_db()
    placeholder.refresh_from_db()
    assert physical.order_id == order.id
    assert placeholder.status == Parcel.Status.CANCELLED
    assert list(_active(order)) == [physical]


@pytest.mark.django_db
def test_sync_attaches_physical_parcel_even_for_unpaid_order(auth_client):
    """Под неоплаченный заказ посылку не заводим — но коробка уже лежит на складе.

    Отсканированная коробка — это факт: товар поехал, а статус заказа просто
    устарел. Новую посылку не создаём, существующую привязываем.
    """
    user = auth_client.user
    physical = _physical(user.cargo, track="REAL-U")

    r = auth_client.post(
        INGEST,
        {"orders": [{"external_order_id": "EXT-U", "track_number": "REAL-U",
                     "status": "pending_payment"}]},
        format="json",
    )
    assert r.status_code == 200, r.data

    physical.refresh_from_db()
    assert physical.user_id == user.id
    assert Parcel.objects.filter(track_number="REAL-U").count() == 1


@pytest.mark.django_db
def test_unpaid_order_without_physical_parcel_still_gets_none(auth_client):
    """Правило «под неоплаченный заказ посылку не заводим» не сломано."""
    auth_client.post(
        INGEST,
        {"orders": [{"external_order_id": "EXT-N", "track_number": "REAL-N",
                     "status": "pending_payment"}]},
        format="json",
    )
    assert not Parcel.objects.filter(track_number="REAL-N").exists()


# --- подтяжка ---


@pytest.mark.django_db
def test_relink_merges_placeholder_instead_of_duplicating(order):
    from django.core.management import call_command

    _placeholder(order)
    physical = _physical(order.user.cargo)

    call_command("relink_pending_parcels", "--apply")

    physical.refresh_from_db()
    assert physical.order_id == order.id
    assert list(_active(order)) == [physical]


@pytest.mark.django_db
def test_relink_skips_order_with_real_parcel(order):
    from django.core.management import call_command

    Parcel.objects.create(
        cargo=order.user.cargo, user=order.user, order=order,
        track_number="OTHER-REAL", status=Parcel.Status.CUSTOMS,
    )
    physical = _physical(order.user.cargo)

    call_command("relink_pending_parcels", "--apply")

    physical.refresh_from_db()
    assert physical.user_id is None
    assert _active(order).count() == 1


# --- починка уже задвоенных ---


@pytest.mark.django_db
def test_merge_command_fixes_existing_duplicate(order):
    """Ровно то, что наделал подбор 01.10: у заказа заглушка и реальная посылка."""
    from django.core.management import call_command

    placeholder = _placeholder(order, status=Parcel.Status.AT_PICKUP_POINT)
    real = Parcel.objects.create(
        cargo=order.user.cargo, user=order.user, order=order,
        client_code=order.user.client_code, track_number="REAL-1",
        status=Parcel.Status.AT_PICKUP_POINT,
    )

    call_command("merge_order_placeholders", "--apply")

    placeholder.refresh_from_db()
    assert placeholder.status == Parcel.Status.CANCELLED
    assert placeholder.is_archived is True
    assert list(_active(order)) == [real]


@pytest.mark.django_db
def test_merge_command_dry_run_changes_nothing(order):
    from django.core.management import call_command

    placeholder = _placeholder(order, status=Parcel.Status.AT_PICKUP_POINT)
    Parcel.objects.create(
        cargo=order.user.cargo, user=order.user, order=order,
        track_number="REAL-1", status=Parcel.Status.AT_PICKUP_POINT,
    )

    call_command("merge_order_placeholders")

    placeholder.refresh_from_db()
    assert placeholder.status == Parcel.Status.AT_PICKUP_POINT


@pytest.mark.django_db
def test_merge_command_leaves_two_real_parcels_alone(order):
    """Две посылки с настоящими треками — не дубль, а две коробки."""
    from django.core.management import call_command

    a = Parcel.objects.create(
        cargo=order.user.cargo, user=order.user, order=order,
        track_number="REAL-1", status=Parcel.Status.AT_PICKUP_POINT,
    )
    b = Parcel.objects.create(
        cargo=order.user.cargo, user=order.user, order=order,
        track_number="REAL-2", status=Parcel.Status.AT_PICKUP_POINT,
    )

    call_command("merge_order_placeholders", "--apply")

    a.refresh_from_db()
    b.refresh_from_db()
    assert a.status == b.status == Parcel.Status.AT_PICKUP_POINT
