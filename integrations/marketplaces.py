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


def _taobao_first(raw: dict, *keys):
    """Taobao раскладывает поля по вложенным блокам — ищем первое непустое."""
    for key in keys:
        value = raw.get(key)
        if isinstance(value, dict):
            continue
        if value not in (None, ""):
            return value
    return None


def normalize_taobao_order(raw: dict):
    """Сырой заказ Taobao → payload, либо None.

    ВНИМАНИЕ: раскладка полей ещё не подтверждена реальными данными.

    Ответ ``queryboughtlistv2`` (проверено вживую 2026-08-08) приходит деревом
    компонентов Ultron — ``data.data`` + ``data.hierarchy`` — а не списком
    заказов с блоками ``statusInfo``/``payInfo``/``subOrders``, как здесь
    предполагается. Эти имена взяты из документации к старой версии API.
    Функция останется рабочей для такого формата, но настоящую раскладку надо
    дописать по ответу, где ``global.orderCount > 0``.

    Пока такого ответа нет, заказы Taobao из WebView сохраняться не будут —
    ingest их просто не опознает и молча пропустит.
    """
    order_info = raw.get("orderInfo") if isinstance(raw.get("orderInfo"), dict) else {}
    status_info = raw.get("statusInfo") if isinstance(raw.get("statusInfo"), dict) else {}
    pay_info = raw.get("payInfo") if isinstance(raw.get("payInfo"), dict) else {}
    logistics = raw.get("logisticsInfo") if isinstance(raw.get("logisticsInfo"), dict) else {}

    order_id = str(
        _taobao_first(raw, "id", "orderId", "bizOrderId")
        or _taobao_first(order_info, "id", "orderId", "bizOrderId")
        or ""
    ).strip()
    if not order_id:
        return None

    prompt = str(
        _taobao_first(status_info, "text", "statusText", "desc")
        or _taobao_first(raw, "statusText", "orderStatus")
        or ""
    )
    track = str(
        _taobao_first(logistics, "mailNo", "logisticsId")
        or _taobao_first(raw, "mailNo")
        or ""
    ).strip()
    status = _status_from_prompt(prompt, track)
    if status is None:
        return None

    sub_orders = raw.get("subOrders")
    sub_orders = sub_orders if isinstance(sub_orders, list) else []
    titles, quantity = [], 0
    for item in sub_orders:
        if not isinstance(item, dict):
            continue
        title = _taobao_first(item, "title", "itemTitle", "name")
        if title:
            titles.append(str(title))
        quantity += int(_taobao_first(item, "quantity", "buyAmount") or 0)
    if not titles:
        title = _taobao_first(raw, "title", "itemTitle")
        if title:
            titles.append(str(title))

    price = _decimal_from_yuan(
        _taobao_first(pay_info, "actualFee", "totalFee", "payFee")
        or _taobao_first(raw, "actualFee", "totalFee")
    )

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
        # Заказ mtop приходит блоками, но набор блоков плавает от версии к
        # версии — признаком считаем любой из них, иначе заказ вида
        # {id, statusInfo} примем за уже нормализованный и потеряем.
        raw_marker=(
            "orderInfo",
            "subOrders",
            "bizOrderId",
            "statusInfo",
            "payInfo",
            "logisticsInfo",
        ),
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
