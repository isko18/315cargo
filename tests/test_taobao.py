"""Интеграция Taobao — тот же контракт, что у Pinduoduo, свой разбор заказов."""

import pytest

from integrations.models import MarketplaceAccount
from integrations.services import TaobaoSyncService
from orders.models import Order


@pytest.mark.django_db
def test_connect_creates_separate_account(auth_client):
    """Подключения к разным маркетплейсам не мешают друг другу."""
    auth_client.post("/api/integrations/pinduoduo/connect/", {}, format="json")
    response = auth_client.post("/api/integrations/taobao/connect/", {}, format="json")

    assert response.status_code == 200
    assert response.data["is_connected"] is True
    assert response.data["marketplace"] == "taobao"

    accounts = MarketplaceAccount.objects.filter(user=auth_client.user)
    assert accounts.count() == 2
    assert set(accounts.values_list("marketplace", flat=True)) == {"pinduoduo", "taobao"}


@pytest.mark.django_db
def test_disconnect_taobao_keeps_pinduoduo(auth_client):
    auth_client.post("/api/integrations/pinduoduo/connect/", {}, format="json")
    auth_client.post("/api/integrations/taobao/connect/", {}, format="json")

    auth_client.post("/api/integrations/taobao/disconnect/")

    assert MarketplaceAccount.objects.get(
        user=auth_client.user, marketplace="pinduoduo"
    ).is_connected is True
    assert MarketplaceAccount.objects.get(
        user=auth_client.user, marketplace="taobao"
    ).is_connected is False


@pytest.mark.django_db
def test_ingest_raw_taobao_filters_and_parses(auth_client):
    """Сырой ответ mtop разбирается на сервере: цена, статус, трек, товары."""
    from parcels.models import Parcel

    raw_orders = [
        {  # оплачен, ждёт отправки
            "id": "TB-1001",
            "statusInfo": {"text": "等待卖家发货"},
            "payInfo": {"actualFee": "129.90"},
            "subOrders": [{"title": "Кроссовки", "quantity": 1}],
        },
        {  # отменён — отбрасываем
            "id": "TB-1002",
            "statusInfo": {"text": "交易关闭"},
            "payInfo": {"actualFee": "50.00"},
            "subOrders": [{"title": "Шапка", "quantity": 1}],
        },
        {  # в пути, с треком → создаётся посылка
            "bizOrderId": "TB-1003",
            "statusInfo": {"text": "卖家已发货"},
            "payInfo": {"actualFee": "1057.30"},
            "logisticsInfo": {"mailNo": "SF-TRACK-9"},
            "subOrders": [
                {"title": "Сканер", "quantity": 2},
                {"title": "Чехол", "quantity": 1},
            ],
        },
    ]
    response = auth_client.post(
        "/api/integrations/taobao/ingest/", {"orders": raw_orders}, format="json"
    )
    assert response.status_code == 200, response.data
    assert response.data["created"] == 2  # отменённый отфильтрован

    user = auth_client.user
    paid = Order.objects.get(user=user, external_order_id="TB-1001")
    assert paid.source == Order.Source.TAOBAO
    assert str(paid.price) == "129.90"
    assert paid.status == Order.Status.PAID
    assert paid.product_title == "Кроссовки"
    # Посылка есть и без трека — по номеру заказа.
    assert Parcel.objects.filter(track_number="TB-1001", user=user).exists()

    assert not Order.objects.filter(external_order_id="TB-1002").exists()

    shipped = Order.objects.get(user=user, external_order_id="TB-1003")
    assert shipped.status == Order.Status.PURCHASED
    assert shipped.track_number == "SF-TRACK-9"
    assert shipped.product_title == "Сканер | Чехол"
    assert shipped.quantity == 3
    assert Parcel.objects.filter(track_number="SF-TRACK-9", user=user).exists()


@pytest.mark.django_db
def test_taobao_completed_order_marked_arrived(auth_client):
    auth_client.post(
        "/api/integrations/taobao/ingest/",
        {
            "orders": [
                {
                    "id": "TB-DONE",
                    "statusInfo": {"text": "交易成功"},
                    "payInfo": {"totalFee": "88.00"},
                    "subOrders": [{"title": "Носки", "quantity": 5}],
                }
            ]
        },
        format="json",
    )
    order = Order.objects.get(external_order_id="TB-DONE")
    assert order.status == Order.Status.ARRIVED_CHINA_WAREHOUSE


@pytest.mark.django_db
def test_same_external_id_on_two_marketplaces_not_confused(auth_client):
    """Номера заказов у маркетплейсов независимы — дедуп идёт по источнику."""
    payload = {"orders": [{"id": "SAME-1", "statusInfo": {"text": "等待卖家发货"}}]}
    auth_client.post("/api/integrations/taobao/ingest/", payload, format="json")
    auth_client.post(
        "/api/integrations/pinduoduo/ingest/",
        {"orders": [{"order_sn": "SAME-1", "order_status_prompt": "等待商家发货"}]},
        format="json",
    )

    assert Order.objects.filter(external_order_id="SAME-1").count() == 2
    assert Order.objects.filter(
        external_order_id="SAME-1", source=Order.Source.TAOBAO
    ).exists()
    assert Order.objects.filter(
        external_order_id="SAME-1", source=Order.Source.PINDUODUO
    ).exists()


@pytest.mark.django_db
def test_ingest_is_idempotent(auth_client):
    payload = {
        "orders": [
            {
                "id": "TB-IDEM",
                "statusInfo": {"text": "卖家已发货"},
                "logisticsInfo": {"mailNo": "TB-TRACK-IDEM"},
                "payInfo": {"actualFee": "10.00"},
            }
        ]
    }
    first = auth_client.post("/api/integrations/taobao/ingest/", payload, format="json")
    second = auth_client.post("/api/integrations/taobao/ingest/", payload, format="json")

    assert first.data["created"] == 1
    assert second.data["created"] == 0
    assert second.data["updated"] == 1
    assert Order.objects.filter(external_order_id="TB-IDEM").count() == 1


@pytest.mark.django_db
def test_session_expired_records_reason_and_lifetime(auth_client):
    from common.models import AuditLog

    auth_client.post("/api/integrations/taobao/connect/", {}, format="json")
    auth_client.post(
        "/api/integrations/taobao/session-expired/",
        {"reason": "login_redirect"},
        format="json",
    )

    account = MarketplaceAccount.objects.get(
        user=auth_client.user, marketplace="taobao"
    )
    assert account.is_connected is False
    assert account.last_expire_reason == "login_redirect"
    assert account.session_lifetime() is not None
    assert AuditLog.objects.filter(
        action=AuditLog.Action.TAOBAO_SESSION_EXPIRED, target_user=auth_client.user
    ).exists()


@pytest.mark.django_db
def test_garbage_order_does_not_break_import(auth_client):
    """Формат Taobao меняется от версии к версии — мусор не должен ронять импорт."""
    response = auth_client.post(
        "/api/integrations/taobao/ingest/",
        {
            "orders": [
                {"statusInfo": {"text": "等待卖家发货"}},  # без id
                {"id": "TB-OK", "statusInfo": {"text": "等待卖家发货"}},
                {"id": "TB-BADFEE", "statusInfo": {"text": "等待卖家发货"},
                 "payInfo": {"actualFee": "не число"}},
            ]
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    assert Order.objects.filter(external_order_id="TB-OK").exists()
    # Кривая сумма не роняет заказ — просто остаётся пустой.
    assert Order.objects.get(external_order_id="TB-BADFEE").price is None


@pytest.mark.django_db
def test_sync_without_connection_is_noop(user):
    service = TaobaoSyncService(user)
    result = service.sync_orders()
    assert result.synced == 0
    assert "не подключён" in result.message
