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
