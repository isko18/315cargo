import pytest

from integrations.models import PinduoduoAccount
from integrations.pinduoduo.services import PinduoduoSyncService
from orders.models import Order


class FakeClient:
    def __init__(self, orders):
        self.orders = orders

    def fetch_orders(self, session_data):
        return self.orders


@pytest.mark.django_db
def test_connect_creates_account(auth_client):
    response = auth_client.post(
        "/api/integrations/pinduoduo/connect/", {"session_data": {"foo": "bar"}}, format="json"
    )
    assert response.status_code == 200
    assert response.data["is_connected"] is True

    account = PinduoduoAccount.objects.get(user=auth_client.user)
    assert account.session_data == {"foo": "bar"}


@pytest.mark.django_db
def test_disconnect(auth_client):
    auth_client.post(
        "/api/integrations/pinduoduo/connect/", {"session_data": {}}, format="json"
    )
    response = auth_client.post("/api/integrations/pinduoduo/disconnect/")
    assert response.status_code == 200
    assert response.data["is_connected"] is False


@pytest.mark.django_db
def test_sync_creates_orders_via_client(user):
    fake = FakeClient(
        [
            {
                "external_order_id": "PDD-1",
                "product_title": "Чашка",
                "price": "100.50",
                "quantity": 2,
                "status": "paid",
            },
            {
                "external_order_id": "PDD-2",
                "product_title": "Платок",
                "price": "50",
                "status": "shipped",
            },
        ]
    )
    service = PinduoduoSyncService(user, client=fake)
    service.connect({"any": "thing"})
    result = service.sync_orders()
    assert result.synced == 2
    assert result.created == 2
    assert Order.objects.filter(user=user, source=Order.Source.PINDUODUO).count() == 2


@pytest.mark.django_db
def test_sync_updates_existing_order(user):
    fake_v1 = FakeClient([{"external_order_id": "PDD-X", "status": "paid"}])
    service = PinduoduoSyncService(user, client=fake_v1)
    service.connect()
    service.sync_orders()

    fake_v2 = FakeClient(
        [{"external_order_id": "PDD-X", "status": "shipped", "track_number": "LP123"}]
    )
    service.client = fake_v2
    result = service.sync_orders()
    assert result.created == 0
    assert result.updated == 1
    order = Order.objects.get(user=user, external_order_id="PDD-X")
    assert order.track_number == "LP123"
    assert order.status == Order.Status.PURCHASED


@pytest.mark.django_db
def test_order_dedup_constraint(user):
    from django.db import IntegrityError

    Order.objects.create(
        user=user, source=Order.Source.PINDUODUO, external_order_id="DUP-1"
    )
    with pytest.raises(IntegrityError):
        Order.objects.create(
            user=user, source=Order.Source.PINDUODUO, external_order_id="DUP-1"
        )


@pytest.mark.django_db
def test_manual_orders_with_blank_external_id_allowed(user):
    # Blank external_order_id is exempt from the unique constraint.
    Order.objects.create(user=user, source=Order.Source.MANUAL)
    Order.objects.create(user=user, source=Order.Source.MANUAL)
    assert Order.objects.filter(user=user, source=Order.Source.MANUAL).count() == 2


@pytest.mark.django_db
def test_ingest_creates_orders_and_parcels(auth_client):
    from parcels.models import Parcel

    response = auth_client.post(
        "/api/integrations/pinduoduo/ingest/",
        {
            "orders": [
                {
                    "external_order_id": "ING-1",
                    "product_title": "Куртка",
                    "price": "120.00",
                    "status": "shipped",
                    "track_number": "LPNINGEST1",
                },
                {"external_order_id": "ING-2", "product_title": "Без трека"},
            ]
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    assert response.data["created"] == 2

    user = auth_client.user
    assert Order.objects.filter(user=user, external_order_id="ING-1").exists()
    # Посылка создана по трек-номеру и привязана к заказу/клиенту.
    parcel = Parcel.objects.get(track_number="LPNINGEST1")
    assert parcel.user_id == user.id
    assert parcel.order.external_order_id == "ING-1"
    assert parcel.client_code == user.client_code
    # Заказ без реального трека тоже даёт посылку — по номеру заказа.
    p2 = Parcel.objects.get(order__external_order_id="ING-2")
    assert p2.track_number == "ING-2"


@pytest.mark.django_db
def test_ingest_raw_pdd_filters_and_parses(auth_client):
    from parcels.models import Parcel

    raw_orders = [
        {  # ждёт отправки, оплачено 0.98
            "order_sn": "260624-AAA",
            "order_status_prompt": "免拼成功，待发货",
            "order_amount": 98,
            "tracking_number": "",
            "order_goods": [{"goods_name": "Органайзер", "goods_number": 1}],
        },
        {  # отменён — должен быть отброшен
            "order_sn": "260622-CANCEL",
            "order_status_prompt": "交易已取消",
            "order_amount": 81480,
            "order_goods": [{"goods_name": "X", "goods_number": 10}],
        },
        {  # в пути, с треком → создастся посылка
            "order_sn": "260620-SHIP",
            "order_status_prompt": "待收货",
            "order_amount": 105730,
            "tracking_number": "LP-TRACK-1",
            "order_goods": [{"goods_name": "Сканер", "goods_number": 2}],
        },
    ]
    r = auth_client.post(
        "/api/integrations/pinduoduo/ingest/", {"orders": raw_orders}, format="json"
    )
    assert r.status_code == 200, r.data
    assert r.data["created"] == 2  # отменённый отфильтрован

    user = auth_client.user
    paid = Order.objects.get(user=user, external_order_id="260624-AAA")
    assert str(paid.price) == "0.98"            # цена поделена на 100
    assert paid.status == Order.Status.PAID
    assert paid.product_title == "Органайзер"
    # посылка создаётся и для «ждёт отправки» — по номеру заказа (трека ещё нет)
    assert Parcel.objects.filter(track_number="260624-AAA", user=user).exists()
    # отменённый не сохранён
    assert not Order.objects.filter(external_order_id="260622-CANCEL").exists()

    ship = Order.objects.get(user=user, external_order_id="260620-SHIP")
    assert str(ship.price) == "1057.30"
    assert ship.status == Order.Status.PURCHASED
    # по заказу в пути с треком создана посылка
    assert Parcel.objects.filter(track_number="LP-TRACK-1", user=user).exists()


@pytest.mark.django_db
def test_ingest_normalized_with_raw_is_filtered(auth_client):
    # Старое приложение шлёт нормализованный payload, но с сырым заказом в `raw`.
    # Сервер всё равно фильтрует по raw и проставляет статус/цену.
    payload = {
        "orders": [
            {  # отменённый внутри raw → отбрасывается, несмотря на external_order_id
                "external_order_id": "260622-CANCEL",
                "status": "created",
                "raw": {
                    "order_sn": "260622-CANCEL",
                    "order_status_prompt": "交易已取消",
                    "order_amount": 81480,
                    "order_goods": [{"goods_name": "X", "goods_number": 1}],
                },
            },
            {  # получен → сохраняется как ARRIVED_CHINA_WAREHOUSE
                "external_order_id": "260620-DONE",
                "status": "created",
                "raw": {
                    "order_sn": "260620-DONE",
                    "order_status_prompt": "交易成功",
                    "order_amount": 5000,
                    "tracking_number": "LP-DONE",
                    "order_goods": [{"goods_name": "Готово", "goods_number": 1}],
                },
            },
        ]
    }
    r = auth_client.post(
        "/api/integrations/pinduoduo/ingest/", payload, format="json"
    )
    assert r.status_code == 200, r.data
    assert r.data["created"] == 1  # отменённый отфильтрован
    assert not Order.objects.filter(external_order_id="260622-CANCEL").exists()
    done = Order.objects.get(external_order_id="260620-DONE")
    assert done.status == Order.Status.ARRIVED_CHINA_WAREHOUSE  # получен
    assert str(done.price) == "50.00"


@pytest.mark.django_db
def test_ingest_dedup_and_parcel_owner_guard(auth_client):
    from parcels.models import Parcel
    from tests.factories import ParcelFactory

    # Чужая посылка с тем же треком не должна быть украдена/переписана.
    foreign = ParcelFactory(track_number="SHARED-TRACK")

    payload = {
        "orders": [
            {"external_order_id": "DUP-A", "track_number": "SHARED-TRACK"},
        ]
    }
    r1 = auth_client.post("/api/integrations/pinduoduo/ingest/", payload, format="json")
    r2 = auth_client.post("/api/integrations/pinduoduo/ingest/", payload, format="json")
    assert r1.status_code == 200 and r2.status_code == 200
    # Дедуп: один заказ, не два.
    assert Order.objects.filter(user=auth_client.user, external_order_id="DUP-A").count() == 1
    # Посылка осталась за прежним владельцем.
    assert Parcel.objects.get(track_number="SHARED-TRACK").user_id == foreign.user_id


@pytest.mark.django_db
def test_session_expired_marks_account_and_notifies(auth_client):
    from notifications.models import Notification

    response = auth_client.post(
        "/api/integrations/pinduoduo/session-expired/", {}, format="json"
    )
    assert response.status_code == 200
    assert response.data["is_connected"] is False
    assert Notification.objects.filter(
        user=auth_client.user, data__reason="session_expired"
    ).exists()


@pytest.mark.django_db
def test_webhook_requires_admin(auth_client):
    response = auth_client.post(
        "/api/integrations/pinduoduo/webhook/",
        {"client_code": "X", "orders": []},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_webhook_admin_ingests_orders(staff_client, user):
    response = staff_client.post(
        "/api/integrations/pinduoduo/webhook/",
        {
            "client_code": user.client_code,
            "orders": [
                {"external_order_id": "W-1", "status": "paid", "product_title": "X"},
            ],
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    assert response.data["synced"] == 1
    assert Order.objects.filter(
        user=user, source=Order.Source.PINDUODUO, external_order_id="W-1"
    ).exists()
