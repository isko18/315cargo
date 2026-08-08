"""Интеграция Taobao — тот же контракт, что у Pinduoduo, свой разбор заказов.

Ответ ``queryboughtlistv2`` приходит деревом компонентов Ultron: один заказ
размазан по ``Main_<id>``, ``sellerInfo_<id>``, ``item_<id>_1_1``, ``pay_<id>/0``,
связанным общим id в имени компонента. Структура и имена полей сняты с живого
аккаунта 2026-08-08 — тесты строят ответы в этом же виде.
"""

import json
from pathlib import Path

import pytest

from integrations.models import MarketplaceAccount
from integrations.services import TaobaoSyncService
from orders.models import Order

FIXTURE = Path(__file__).parent / "fixtures" / "taobao_boughtlist.json"


def real_response():
    """Настоящий ответ Taobao с одним заказом (личные данные заменены)."""
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def response_with(*orders):
    """Собрать ответ Ultron из описаний заказов.

    order = {"id": ..., "status": "买家已付款", "wait": "待发货",
             "fee": "61,83 сом", "title": ..., "qty": 1, "track": "SF1"}
    """
    components = {"query3": {"fields": {}}, "tab3": {"fields": {}}}
    structure = {"boughtlist4": ["query3", "tab3"]}
    for order in orders:
        oid = order["id"]
        components[f"Main_{oid}"] = {"fields": {"orderId": oid}}
        if order.get("status"):
            components[f"sellerInfo_{oid}"] = {
                "fields": {"status": {"text": order["status"]}}
            }
        if order.get("wait"):
            components[f"mainWaitSendShipTime_{oid}"] = {
                "fields": {"title": order["wait"]}
            }
        if order.get("fee") is not None:
            components[f"pay_{oid}/0"] = {
                "fields": {"actualFee": {"value": order["fee"]}}
            }
        if order.get("title"):
            components[f"item_{oid}_1_1"] = {
                "fields": {
                    "item": {
                        "title": order["title"],
                        "quantity": order.get("qty", 1),
                        "priceInfo": {"actualTotalFee": order.get("itemFee")},
                    }
                }
            }
        if order.get("track"):
            components[f"mainLogistics_{oid}"] = {
                "fields": {"title": order.get("wait") or "", "mailNo": order["track"]}
            }
        structure["boughtlist4"].append(f"MainGroup_{oid}")
    return {
        "api": "mtop.taobao.order.queryboughtlistv2",
        "ret": ["SUCCESS::调用成功"],
        "data": {
            "data": components,
            "hierarchy": {"root": "boughtlist4", "structure": structure},
            "global": {"orderCount": len(orders)},
        },
    }


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


# --- разбор реального ответа ------------------------------------------------


@pytest.mark.django_db
def test_real_response_parsed(auth_client):
    """Заказ собирается из дерева компонентов, а не из плоского списка."""
    from parcels.models import Parcel

    response = auth_client.post(
        "/api/integrations/taobao/ingest/", {"orders": [real_response()]}, format="json"
    )
    assert response.status_code == 200, response.data
    assert response.data["created"] == 1

    order = Order.objects.get(external_order_id="9900112233445566778")
    assert order.source == Order.Source.TAOBAO
    assert order.status == Order.Status.PAID     # 买家已付款 / 待发货
    assert str(order.price) == "61.83"           # «61,83 сом» → число
    assert order.quantity == 1
    assert "耳罩" in order.product_title
    assert order.track_number == ""              # ещё не отправлен
    # Пока трека нет, посылка заводится по номеру заказа.
    assert Parcel.objects.filter(track_number="9900112233445566778").exists()


@pytest.mark.django_db
def test_real_response_is_idempotent(auth_client):
    payload = {"orders": [real_response()]}
    auth_client.post("/api/integrations/taobao/ingest/", payload, format="json")
    second = auth_client.post("/api/integrations/taobao/ingest/", payload, format="json")

    assert second.data["created"] == 0
    assert second.data["updated"] == 1
    assert Order.objects.filter(external_order_id="9900112233445566778").count() == 1


@pytest.mark.django_db
def test_service_components_are_not_orders(auth_client):
    """query3/tab3/feedStream — служебные компоненты, заказами не являются."""
    auth_client.post(
        "/api/integrations/taobao/ingest/", {"orders": [real_response()]}, format="json"
    )
    assert Order.objects.count() == 1


@pytest.mark.django_db
def test_shipped_order_gets_track_and_parcel(auth_client):
    from parcels.models import Parcel

    payload = response_with(
        {
            "id": "8800000000000000001",
            "status": "卖家已发货",
            "wait": "待收货",
            "fee": "1 057,30 сом",
            "title": "Сканер",
            "qty": 2,
            "track": "SF-TRACK-9",
        }
    )
    auth_client.post("/api/integrations/taobao/ingest/", {"orders": [payload]}, format="json")

    order = Order.objects.get(external_order_id="8800000000000000001")
    assert order.status == Order.Status.PURCHASED
    assert order.track_number == "SF-TRACK-9"
    assert str(order.price) == "1057.30"
    assert order.quantity == 2
    assert Parcel.objects.filter(track_number="SF-TRACK-9").exists()


@pytest.mark.django_db
def test_completed_order_marked_arrived(auth_client):
    payload = response_with(
        {"id": "8800000000000000002", "status": "交易成功", "fee": "88,00 сом", "title": "Носки"}
    )
    auth_client.post("/api/integrations/taobao/ingest/", {"orders": [payload]}, format="json")

    order = Order.objects.get(external_order_id="8800000000000000002")
    assert order.status == Order.Status.ARRIVED_CHINA_WAREHOUSE


@pytest.mark.django_db
def test_cancelled_and_unpaid_are_filtered(auth_client):
    payload = response_with(
        {"id": "8800000000000000003", "status": "交易关闭", "fee": "99,00 сом", "title": "Отменённый"},
        {"id": "8800000000000000004", "status": "待付款", "fee": "10,00 сом", "title": "Неоплаченный"},
        {"id": "8800000000000000005", "status": "买家已付款", "fee": "12,00 сом", "title": "Оплаченный"},
    )
    response = auth_client.post(
        "/api/integrations/taobao/ingest/", {"orders": [payload]}, format="json"
    )

    assert response.data["created"] == 1
    assert Order.objects.filter(external_order_id="8800000000000000005").exists()
    assert not Order.objects.filter(external_order_id="8800000000000000003").exists()
    assert not Order.objects.filter(external_order_id="8800000000000000004").exists()


@pytest.mark.django_db
def test_price_falls_back_to_items_when_no_pay_block(auth_client):
    """Блок с итогом бывает не всегда — тогда складываем позиции."""
    payload = response_with(
        {
            "id": "8800000000000000006",
            "status": "买家已付款",
            "fee": None,
            "title": "Без итога",
            "itemFee": "34,83 сом",
        }
    )
    auth_client.post("/api/integrations/taobao/ingest/", {"orders": [payload]}, format="json")

    assert str(Order.objects.get(external_order_id="8800000000000000006").price) == "34.83"


@pytest.mark.django_db
def test_same_external_id_on_two_marketplaces_not_confused(auth_client):
    """Номера заказов у маркетплейсов независимы — дедуп идёт по источнику."""
    auth_client.post(
        "/api/integrations/taobao/ingest/",
        {"orders": [response_with({"id": "1234567890", "status": "买家已付款", "title": "TB"})]},
        format="json",
    )
    auth_client.post(
        "/api/integrations/pinduoduo/ingest/",
        {"orders": [{"order_sn": "1234567890", "order_status_prompt": "等待商家发货"}]},
        format="json",
    )

    assert Order.objects.filter(external_order_id="1234567890").count() == 2


@pytest.mark.django_db
def test_unknown_shape_does_not_break_import(auth_client):
    """Формат Taobao меняется — незнакомый ответ не должен ронять импорт."""
    response = auth_client.post(
        "/api/integrations/taobao/ingest/",
        {"orders": [{"data": {"data": {"whatever": {"fields": {}}}}}, {"мусор": 1}]},
        format="json",
    )
    assert response.status_code == 200, response.data
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_session_expired_records_reason_and_lifetime(auth_client):
    from common.models import AuditLog

    auth_client.post("/api/integrations/taobao/connect/", {}, format="json")
    auth_client.post(
        "/api/integrations/taobao/session-expired/",
        {"reason": "login_redirect"},
        format="json",
    )

    account = MarketplaceAccount.objects.get(user=auth_client.user, marketplace="taobao")
    assert account.is_connected is False
    assert account.last_expire_reason == "login_redirect"
    assert account.session_lifetime() is not None
    assert AuditLog.objects.filter(
        action=AuditLog.Action.TAOBAO_SESSION_EXPIRED, target_user=auth_client.user
    ).exists()


@pytest.mark.django_db
def test_sync_without_connection_is_noop(user):
    service = TaobaoSyncService(user)
    result = service.sync_orders()
    assert result.synced == 0
    assert "не подключён" in result.message


# --- разбор суммы -----------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("61,83 сом", "61.83"),        # запятая — дробный разделитель
        ("61,83 сом", "61.83"),   # неразрывный пробел перед валютой
        ("¥1,234.56", "1234.56"),      # запятая — разряды
        ("1.234,56 сом", "1234.56"),   # европейская запись
        ("34.83", "34.83"),
        ("бесплатно", None),
        ("", None),
    ],
)
def test_money_string_parsing(text, expected):
    """Сумму Taobao отдаёт строкой с валютой, числом — никогда."""
    from integrations.marketplaces import _decimal_from_money

    result = _decimal_from_money(text)
    assert (str(result) if result is not None else None) == expected


# --- команда проверки раскладки --------------------------------------------


@pytest.mark.django_db
def test_parse_check_on_real_response(tmp_path):
    """Проверка раскладки на реальном ответе — без записи в базу."""
    from io import StringIO

    from django.core.management import call_command

    src = tmp_path / "orders.json"
    src.write_text(
        "mtopjsonp3(" + json.dumps(real_response(), ensure_ascii=False) + ")",
        encoding="utf-8",
    )
    out = StringIO()
    call_command(
        "marketplace_parse_check", "--marketplace", "taobao", "--file", str(src), stdout=out
    )
    text = out.getvalue()

    assert "9900112233445566778" in text
    assert "61.83" in text
    assert "совпала полностью" in text
    assert not Order.objects.filter(external_order_id="9900112233445566778").exists()


@pytest.mark.django_db
def test_parse_check_recognises_expired_session_envelope(tmp_path):
    """Ответ без сессии приходит с HTTP 200 — распознаём его по конверту mtop."""
    from django.core.management import call_command
    from django.core.management.base import CommandError

    src = tmp_path / "expired.json"
    src.write_text(
        'mtopjsonp3({"api":"mtop.taobao.order.queryboughtlistv2","data":{},'
        '"ret":["FAIL_SYS_SESSION_EXPIRED::Session过期"],"v":"1.0"})',
        encoding="utf-8",
    )
    with pytest.raises(CommandError, match="без сессии"):
        call_command("marketplace_parse_check", "--marketplace", "taobao", "--file", str(src))
