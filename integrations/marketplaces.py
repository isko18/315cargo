"""Описание маркетплейсов и разбор их сырых заказов.

Интеграции устроены одинаково: клиент логинится в WebView приложения, оттуда
перехватываются сырые ответы списка заказов и уходят к нам в ``/ingest/``.
Отличаются маркетплейсы только тремя вещами — источником заказа, названиями
событий и форматом сырого ответа. Всё это собрано здесь, поэтому следующий
маркетплейс (1688) добавляется одной записью в ``MARKETPLACES``, а не копией
всего модуля.

Разбор намеренно живёт на сервере: правки в фильтрах и статусах не должны
требовать пересборки мобильного приложения.
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from common.models import AuditLog
from notifications.models import NotificationType
from orders.models import Order

PINDUODUO = "pinduoduo"
TAOBAO = "taobao"

# Статусы, которые нам интересны. Всё, что не оплачено/отменено/возвращено,
# в заказы не попадает: карго везёт только реально купленное.
STATUS_PAID = "paid"          # оплачен, ждёт отправки
STATUS_SHIPPED = "shipped"    # отправлен / в пути
STATUS_DELIVERED = "delivered"  # получен продавцом-складом / завершён


def _decimal_from_fen(value):
    """Суммы PDD приходят в фэнях (копейках): 81480 → 814.80."""
    if not isinstance(value, (int, float)):
        return None
    return (Decimal(str(value)) / 100).quantize(Decimal("0.01"))


def _decimal_from_yuan(value):
    """Taobao отдаёт сумму строкой в юанях: «814.80» → Decimal('814.80')."""
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip()).quantize(Decimal("0.01"))
    except Exception:  # noqa: BLE001 — мусор в поле суммы не должен ронять импорт
        return None


# Формулировки статусов у обоих маркетплейсов китайские и различаются, но
# ключевые слова общие — держим их в одном месте.
_CANCELLED_WORDS = ("取消", "待付款", "待支付", "退款", "已退款", "关闭")
_DONE_WORDS = ("交易成功", "已完成", "已收货", "已签收", "待评价")
_SHIPPED_WORDS = ("待收货", "已发货", "运输", "已送达")


def _status_from_prompt(prompt: str, track: str):
    """Китайская подпись статуса → наш статус. None — заказ не нужен."""
    if any(word in prompt for word in _CANCELLED_WORDS):
        return None
    if any(word in prompt for word in _DONE_WORDS):
        return STATUS_DELIVERED
    if track or any(word in prompt for word in _SHIPPED_WORDS):
        return STATUS_SHIPPED
    return STATUS_PAID


def normalize_pinduoduo_order(raw: dict):
    """Сырой заказ ``order_list_v4`` → payload, либо None если заказ не нужен."""
    sn = str(raw.get("order_sn") or "").strip()
    if not sn:
        return None
    track = str(raw.get("tracking_number") or "").strip()
    status = _status_from_prompt(str(raw.get("order_status_prompt") or ""), track)
    if status is None:
        return None

    goods = raw.get("order_goods")
    goods = goods if isinstance(goods, list) else []
    title = " | ".join(
        str(g.get("goods_name") or "")
        for g in goods
        if isinstance(g, dict) and g.get("goods_name")
    )
    quantity = sum(int(g.get("goods_number") or 0) for g in goods if isinstance(g, dict))

    return {
        "external_order_id": sn,
        "product_title": title[:250],
        "price": _decimal_from_fen(raw.get("order_amount")),
        "quantity": quantity or 1,
        "status": status,
        "track_number": track,
        "raw": raw,
    }


def _decimal_from_money(value):
    """Строка с суммой → Decimal. Пусто/мусор → None.

    Taobao отдаёт сумму **готовой строкой с валютой**, а не числом: «61,83 сом»
    (валюта зависит от страны аккаунта). Разделителем дробной части может быть
    запятая, внутри встречается неразрывный пробел.
    """
    if value in (None, ""):
        return None
    text = str(value).replace("\u00a0", " ").strip()
    match = re.search(r"\d[\d\s.,]*", text)
    if not match:
        return None
    number = match.group(0).replace(" ", "")
    if "," in number and "." in number:
        # «1.234,56» → запятая дробная; «1,234.56» → запятая разрядная.
        number = (
            number.replace(",", "")
            if number.rfind(".") > number.rfind(",")
            else number.replace(".", "").replace(",", ".")
        )
    elif "," in number:
        number = (
            number.replace(",", ".")
            if re.search(r",\d{1,2}$", number)
            else number.replace(",", "")
        )
    try:
        return Decimal(number).quantize(Decimal("0.01"))
    except Exception:  # noqa: BLE001 — мусор в сумме не должен ронять импорт
        return None


def _deep_find(node, pattern, depth=0):
    """Первое значение, чей ключ подходит под регулярку.

    Нужно для полей, чьё место в дереве плавает: например трек-номер появляется
    только у отправленного заказа и в отдельном блоке.
    """
    if depth > 6:
        return None
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, (str, int)) and pattern.search(key) and str(value).strip():
                return str(value).strip()
            found = _deep_find(value, pattern, depth + 1)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _deep_find(item, pattern, depth + 1)
            if found:
                return found
    return None


_TRACK_KEY_RE = re.compile(r"mailno|logisticsid|expressno|trackingno", re.I)
# id заказа зашит в имя компонента: Main_5127…, item_5127…_1_1, pay_5127…/0
_COMPONENT_ORDER_ID_RE = re.compile(r"^(?P<name>[A-Za-z]+)_(?P<oid>\d{6,})")


def extract_taobao_orders(response):
    """Полный ответ ``queryboughtlistv2`` → список заказов.

    Ответ приходит деревом компонентов Ultron: один заказ размазан по
    ``Main_<id>``, ``sellerInfo_<id>``, ``item_<id>_1_1``, ``pay_<id>/0``,
    связанным общим id в имени компонента. Собираем их обратно в один объект.
    Структура подтверждена реальным ответом (2026-08-08).
    """
    if not isinstance(response, dict):
        return []
    data = response.get("data") if isinstance(response.get("data"), dict) else response
    components = data.get("data") if isinstance(data.get("data"), dict) else None
    if not isinstance(components, dict):
        return []

    grouped = {}
    for name, component in components.items():
        match = _COMPONENT_ORDER_ID_RE.match(name)
        if not match or not isinstance(component, dict):
            continue
        bucket = grouped.setdefault(match.group("oid"), {})
        bucket.setdefault(match.group("name"), []).append(component.get("fields") or {})

    orders = []
    for order_id, parts in grouped.items():
        # Main есть у настоящего заказа; группы-обёртки (MainGroup, subGroup)
        # полей не несут и заказом не являются.
        if "Main" not in parts:
            continue
        orders.append({"__taobao_order_id": order_id, "parts": parts})
    return orders


def normalize_taobao_order(raw: dict):
    """Собранный заказ Taobao → payload, либо None если заказ не нужен.

    Раскладка проверена на реальном ответе: сумма — в ``pay/actualFee`` строкой
    с валютой, статус — в ``sellerInfo.status.text`` и заголовке блока ожидания,
    товары — в ``item.item``.
    """
    parts = raw.get("parts") if isinstance(raw.get("parts"), dict) else None
    if not parts:
        return None
    main = (parts.get("Main") or [{}])[0]
    order_id = str(raw.get("__taobao_order_id") or main.get("orderId") or "").strip()
    if not order_id:
        return None

    status_texts = []
    for seller in parts.get("sellerInfo", []):
        status = seller.get("status")
        if isinstance(status, dict) and status.get("text"):
            status_texts.append(str(status["text"]))
    for key, blocks in parts.items():
        # mainWaitSendShipTime, mainLogistics и прочие блоки состояния.
        if key.startswith("main"):
            for block in blocks:
                if block.get("title"):
                    status_texts.append(str(block["title"]))
    prompt = " ".join(status_texts)

    track = _deep_find(parts, _TRACK_KEY_RE) or ""
    status = _status_from_prompt(prompt, track)
    if status is None:
        return None

    titles, quantity = [], 0
    for item_fields in parts.get("item", []):
        item = item_fields.get("item")
        if not isinstance(item, dict):
            continue
        if item.get("title"):
            titles.append(str(item["title"]))
        quantity += int(item.get("quantity") or 0)

    price = None
    for pay in parts.get("pay", []):
        fee = pay.get("actualFee")
        if isinstance(fee, dict):
            price = _decimal_from_money(fee.get("value"))
        if price is not None:
            break
    if price is None:
        # Блока с итогом нет — складываем позиции.
        total, seen = Decimal("0"), False
        for item_fields in parts.get("item", []):
            info = (item_fields.get("item") or {}).get("priceInfo")
            if isinstance(info, dict):
                part = _decimal_from_money(info.get("actualTotalFee"))
                if part is not None:
                    total += part
                    seen = True
        price = total if seen else None

    return {
        "external_order_id": order_id,
        "product_title": " | ".join(titles)[:250],
        "price": price,
        "quantity": quantity or 1,
        "status": status,
        "track_number": track,
        "raw": raw,
    }


@dataclass(frozen=True)
class Marketplace:
    key: str
    title: str
    source: str
    normalize: Callable[[dict], dict | None]
    # Признак сырого заказа: по нему отличаем сырой объект от нормализованного.
    raw_marker: tuple[str, ...]
    audit_connected: str
    audit_disconnected: str
    audit_synced: str
    audit_session_expired: str
    notify_connected: str
    notify_synced: str
    # Полный ответ маркетплейса → список сырых заказов. None, если заказы
    # приходят готовым списком и разбирать конверт не нужно (так у PDD).
    extract: Callable[[dict], list] | None = None

    def is_raw(self, payload: dict) -> bool:
        return any(payload.get(marker) for marker in self.raw_marker)


MARKETPLACES = {
    PINDUODUO: Marketplace(
        key=PINDUODUO,
        title="Pinduoduo",
        source=Order.Source.PINDUODUO,
        normalize=normalize_pinduoduo_order,
        raw_marker=("order_sn",),
        audit_connected=AuditLog.Action.PINDUODUO_CONNECTED,
        audit_disconnected=AuditLog.Action.PINDUODUO_DISCONNECTED,
        audit_synced=AuditLog.Action.PINDUODUO_SYNCED,
        audit_session_expired=AuditLog.Action.PINDUODUO_SESSION_EXPIRED,
        notify_connected=NotificationType.PINDUODUO_CONNECTED,
        notify_synced=NotificationType.PINDUODUO_SYNCED,
    ),
    TAOBAO: Marketplace(
        key=TAOBAO,
        title="Taobao",
        source=Order.Source.TAOBAO,
        normalize=normalize_taobao_order,
        # Собранный заказ помечен служебным ключом — по нему и опознаём.
        raw_marker=("__taobao_order_id",),
        extract=extract_taobao_orders,
        audit_connected=AuditLog.Action.TAOBAO_CONNECTED,
        audit_disconnected=AuditLog.Action.TAOBAO_DISCONNECTED,
        audit_synced=AuditLog.Action.TAOBAO_SYNCED,
        audit_session_expired=AuditLog.Action.TAOBAO_SESSION_EXPIRED,
        notify_connected=NotificationType.TAOBAO_CONNECTED,
        notify_synced=NotificationType.TAOBAO_SYNCED,
    ),
}


def get_marketplace(key: str) -> Marketplace:
    try:
        return MARKETPLACES[key]
    except KeyError as exc:
        raise ValueError(f"Неизвестный маркетплейс: {key}") from exc
