"""Интеграция 1688 — третья площадка на том же контракте.

1688 работает на том же движке Alibaba, что и Taobao
(``mtop.alibaba.cbu.wireless.uniform.render.*``, хост ``h5api.m.1688.com``),
поэтому список заказов приходит деревом компонентов Ultron и разбирается общим
кодом. Имена компонентов у 1688 могут отличаться — заказом считается любая
группа, где нашёлся идентификатор заказа.
"""

import pytest

from integrations.models import MarketplaceAccount
from integrations.services import Shop1688SyncService
from orders.models import Order


def ultron_response(*orders, id_field="orderId"):
    """Ответ Ultron с произвольными именами компонентов.

    ``id_field`` позволяет проверить, что разбор не завязан на конкретное имя
    поля с номером заказа: у 1688 оно может называться иначе.
    """
    components = {"header": {"fields": {}}, "filterTab": {"fields": {}}}
    for order in orders:
        oid = order["id"]
        components[f"orderInfo_{oid}"] = {"fields": {id_field: oid}}
        components[f"sellerInfo_{oid}"] = {
            "fields": {"status": {"text": order.get("status", "")}}
        }
        components[f"item_{oid}_1_1"] = {
            "fields": {
                "item": {
                    "title": order.get("title", ""),
                    "quantity": order.get("qty", 1),
                }
            }
        }
        if order.get("fee"):
            components[f"pay_{oid}/0"] = {
                "fields": {"actualFee": {"value": order["fee"]}}
            }
        if order.get("track"):
            components[f"mainLogistics_{oid}"] = {"fields": {"mailNo": order["track"]}}
    return {
        "api": "mtop.alibaba.cbu.wireless.uniform.render.getpagedata",
        "ret": ["SUCCESS::调用成功"],
        "data": {"data": components, "global": {"orderCount": len(orders)}},
    }


@pytest.mark.django_db
def test_three_marketplaces_are_independent(auth_client):
    """Клиент может быть подключён к PDD, Taobao и 1688 одновременно."""
    for market in ("pinduoduo", "taobao", "1688"):
        response = auth_client.post(f"/api/integrations/{market}/connect/", {}, format="json")
        assert response.status_code == 200, response.data
        assert response.data["marketplace"] == market

    accounts = MarketplaceAccount.objects.filter(user=auth_client.user)
    assert set(accounts.values_list("marketplace", flat=True)) == {
        "pinduoduo",
        "taobao",
        "1688",
    }

    # Разлогин одной площадки не трогает остальные.
    auth_client.post("/api/integrations/1688/session-expired/", {"reason": "banned"}, format="json")
    states = dict(accounts.values_list("marketplace", "is_connected"))
    assert states["1688"] is False
    assert states["taobao"] is True
    assert states["pinduoduo"] is True


@pytest.mark.django_db
def test_ingest_parses_order_and_creates_parcel(auth_client):
    from parcels.models import Parcel

    payload = ultron_response(
        {
            "id": "1122334455667788",
            "status": "卖家已发货",
            "fee": "1 250,00 сом",
            "title": "Оптовая партия перчаток",
            "qty": 50,
            "track": "YT-1688-TRACK",
        }
    )
    response = auth_client.post(
        "/api/integrations/1688/ingest/", {"orders": [payload]}, format="json"
    )
    assert response.status_code == 200, response.data
    assert response.data["created"] == 1

    order = Order.objects.get(external_order_id="1122334455667788")
    assert order.source == Order.Source.SHOP_1688
    assert order.status == Order.Status.PURCHASED
    assert str(order.price) == "1250.00"
    assert order.quantity == 50
    assert order.track_number == "YT-1688-TRACK"
    assert Parcel.objects.filter(track_number="YT-1688-TRACK").exists()


@pytest.mark.django_db
def test_order_id_field_may_differ(auth_client):
    """У 1688 поле с номером может называться иначе — разбор не должен ломаться."""
    payload = ultron_response(
        {"id": "2233445566778899", "status": "买家已付款", "title": "Товар"},
        id_field="bizOrderId",
    )
    auth_client.post("/api/integrations/1688/ingest/", {"orders": [payload]}, format="json")

    assert Order.objects.filter(external_order_id="2233445566778899").exists()


@pytest.mark.django_db
def test_service_blocks_are_not_orders(auth_client):
    """header/filterTab — служебные компоненты, заказами их считать нельзя."""
    payload = ultron_response({"id": "3344556677889900", "status": "买家已付款", "title": "X"})
    auth_client.post("/api/integrations/1688/ingest/", {"orders": [payload]}, format="json")

    assert Order.objects.count() == 1


@pytest.mark.django_db
def test_statuses_recognised_and_parcel_only_for_real(auth_client):
    from parcels.models import Parcel

    payload = ultron_response(
        {"id": "4400000000000001", "status": "交易关闭", "title": "Отменённый"},
        {"id": "4400000000000002", "status": "待付款", "title": "Неоплаченный"},
        {"id": "4400000000000003", "status": "买家已付款", "title": "Оплаченный"},
    )
    response = auth_client.post(
        "/api/integrations/1688/ingest/", {"orders": [payload]}, format="json"
    )

    assert response.data["created"] == 3  # сохраняем все
    statuses = dict(
        Order.objects.filter(source=Order.Source.SHOP_1688).values_list(
            "external_order_id", "status"
        )
    )
    assert statuses["4400000000000001"] == Order.Status.CANCELLED
    assert statuses["4400000000000002"] == Order.Status.CREATED
    assert statuses["4400000000000003"] == Order.Status.PAID
    # Посылка только под то, что реально поедет.
    assert not Parcel.objects.filter(track_number="4400000000000001").exists()
    assert Parcel.objects.filter(track_number="4400000000000003").exists()


@pytest.mark.django_db
def test_same_order_id_on_three_marketplaces(auth_client):
    """Номера заказов площадок независимы — дедуп идёт по источнику."""
    auth_client.post(
        "/api/integrations/1688/ingest/",
        {"orders": [ultron_response({"id": "555000111", "status": "买家已付款", "title": "A"})]},
        format="json",
    )
    auth_client.post(
        "/api/integrations/taobao/ingest/",
        {"orders": [ultron_response({"id": "555000111", "status": "买家已付款", "title": "B"})]},
        format="json",
    )
    auth_client.post(
        "/api/integrations/pinduoduo/ingest/",
        {"orders": [{"order_sn": "555000111", "order_status_prompt": "等待商家发货"}]},
        format="json",
    )

    assert Order.objects.filter(external_order_id="555000111").count() == 3


@pytest.mark.django_db
def test_parcel_source_and_filter(auth_client):
    """Мобилка фильтрует посылки по площадке — 1688 не должен выпадать."""
    auth_client.post(
        "/api/integrations/1688/ingest/",
        {
            "orders": [
                ultron_response(
                    {
                        "id": "6600000000000001",
                        "status": "卖家已发货",
                        "title": "Партия",
                        "track": "TRACK-1688-F",
                    }
                )
            ]
        },
        format="json",
    )

    rows = auth_client.get("/api/parcels/?source=1688").data
    assert {r["track_number"] for r in rows} == {"TRACK-1688-F"}
    assert rows[0]["source"] == "1688"
    assert rows[0]["source_display_name"] == "1688"


@pytest.mark.django_db
def test_sync_without_connection_is_noop(user):
    service = Shop1688SyncService(user)
    result = service.sync_orders()
    assert result.synced == 0
    assert "не подключён" in result.message


@pytest.mark.django_db
def test_parse_check_supports_1688(tmp_path):
    """Раскладку 1688 можно проверить на реальном ответе без записи в базу."""
    import json
    from io import StringIO

    from django.core.management import call_command

    src = tmp_path / "orders.json"
    src.write_text(
        json.dumps(
            ultron_response(
                {"id": "7700000000000001", "status": "买家已付款", "fee": "99,00 сом", "title": "Проверка"}
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out = StringIO()
    call_command("marketplace_parse_check", "--marketplace", "1688", "--file", str(src), stdout=out)
    text = out.getvalue()

    assert "7700000000000001" in text
    assert "99.00" in text
    assert not Order.objects.filter(external_order_id="7700000000000001").exists()
