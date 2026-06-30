"""Pinduoduo integration layer.

Высокорисковый модуль (ТЗ п.13.1). Здесь намеренно не реализован парсинг
веб-страниц или скрэйп Pinduoduo: эти подходы нестабильны и могут нарушать
TOS. Слой задаёт контракт `PinduoduoClient`, конкретная реализация которого
подключается отдельно (official partner API, in-app WebView session,
webhook от сервера-парсера и т.д.).

Контракт:
    PinduoduoClient.fetch_orders(session_data) -> list[OrderPayload]

OrderPayload (dict) поля:
    external_order_id: str    обязательно
    product_url: str          опционально
    product_title: str        опционально
    price: Decimal | str      опционально
    quantity: int             опционально
    status: str               опционально, маппится в Order.Status
    track_number: str         опционально
    raw: dict                 любые сырые данные
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Iterable, Protocol

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from common.audit import log_audit
from common.models import AuditLog
from integrations.models import PinduoduoAccount
from notifications.models import NotificationType
from notifications.services import notify
from orders.models import Order

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    synced: int = 0
    created: int = 0
    updated: int = 0
    message: str = ""
    errors: list[str] = field(default_factory=list)


class PinduoduoClient(Protocol):
    def fetch_orders(self, session_data: dict) -> Iterable[dict]: ...


class NullPinduoduoClient:
    """Default no-op client. Returns no orders.

    Replace with a real implementation when an integration is available."""

    def fetch_orders(self, session_data: dict) -> Iterable[dict]:
        return []


def get_default_client() -> PinduoduoClient:
    path = getattr(settings, "PINDUODUO_CLIENT_PATH", "") or ""
    if not path:
        return NullPinduoduoClient()
    try:
        module_name, attr_name = path.rsplit(".", 1)
        from importlib import import_module

        module = import_module(module_name)
        client_cls = getattr(module, attr_name)
        return client_cls()
    except Exception:
        logger.exception("Failed to load Pinduoduo client %s, falling back to null", path)
        return NullPinduoduoClient()


SOURCE_STATUS_MAP = {
    "pending_payment": Order.Status.CREATED,
    "paid": Order.Status.PAID,
    "shipped": Order.Status.PURCHASED,
    "delivered": Order.Status.ARRIVED_CHINA_WAREHOUSE,
    "cancelled": Order.Status.CANCELLED,
}


def _to_decimal(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


class PinduoduoSyncService:
    def __init__(self, user, client: PinduoduoClient | None = None):
        self.user = user
        self.account, _ = PinduoduoAccount.objects.get_or_create(user=user)
        self.client = client or get_default_client()

    def connect(self, session_data: dict | None = None, *, request=None):
        self.account.is_connected = True
        if not self.account.external_user_id:
            self.account.external_user_id = (session_data or {}).get(
                "external_user_id", f"pdd-{self.user.id}"
            )
        self.account.session_data = session_data or {}
        self.account.last_sync_error = ""
        self.account.save(
            update_fields=(
                "is_connected",
                "external_user_id",
                "session_data",
                "last_sync_error",
                "updated_at",
            )
        )
        log_audit(
            AuditLog.Action.PINDUODUO_CONNECTED,
            actor=self.user,
            target_user=self.user,
            request=request,
        )
        notify(
            self.user,
            title="Pinduoduo подключён",
            body="Ваш аккаунт Pinduoduo успешно подключён. Заказы будут синхронизироваться автоматически.",
            type=NotificationType.PINDUODUO_CONNECTED,
            data={"external_user_id": self.account.external_user_id},
        )
        return self.account

    def disconnect(self, *, request=None):
        self.account.is_connected = False
        self.account.session_data = {}
        self.account.save(
            update_fields=("is_connected", "session_data", "updated_at")
        )
        log_audit(
            AuditLog.Action.PINDUODUO_DISCONNECTED,
            actor=self.user,
            target_user=self.user,
            request=request,
        )
        return self.account

    # --- общий маппинг и сохранение заказов ---

    def _order_defaults(self, payload: dict) -> dict:
        mapped_status = SOURCE_STATUS_MAP.get(
            (payload.get("status") or "").lower(), Order.Status.CREATED
        )
        return {
            "user": self.user,
            "source": Order.Source.PINDUODUO,
            "product_url": payload.get("product_url", ""),
            "product_title": payload.get("product_title", ""),
            "price": _to_decimal(payload.get("price")),
            "quantity": int(payload.get("quantity") or 1),
            "status": mapped_status,
            "track_number": (payload.get("track_number") or "").strip(),
            "raw_data": payload.get("raw") or {},
        }

    def _normalize_pdd_order(self, raw: dict):
        """Сырой заказ order_list_v4 → нормализованный payload, либо None.

        Возвращает None для заказов, которые НЕ нужны (отменён, не оплачен,
        возврат). Оставляем только реально оплаченные: «ждут отправки» и «в пути».
        """
        sn = str(raw.get("order_sn") or "").strip()
        if not sn:
            return None
        prompt = str(raw.get("order_status_prompt") or "")
        track = str(raw.get("tracking_number") or "").strip()

        # Чёрный список: отбрасываем ТОЛЬКО отменённые/неоплаченные/возврат.
        # Всё остальное (ждёт отправки — как бы ни звучал текст, в пути, получен)
        # оставляем. Так заказ 待发货 не теряется из-за непривычной формулировки.
        if any(k in prompt for k in ("取消", "待付款", "待支付", "退款", "已退款")):
            return None  # отменён / не оплачен / возврат — НЕ парсим
        if any(k in prompt for k in ("交易成功", "已完成", "已收货", "已签收", "待评价")):
            status = "delivered"  # получен/завершён (проверяем раньше «待收货»)
        elif track or any(k in prompt for k in ("待收货", "已发货", "运输", "已送达")):
            status = "shipped"  # отправлен / в пути
        else:
            status = "paid"  # ждёт отправки (любая формулировка) / прочее активное

        goods = raw.get("order_goods")
        goods = goods if isinstance(goods, list) else []
        title = " | ".join(
            str(g.get("goods_name") or "")
            for g in goods
            if isinstance(g, dict) and g.get("goods_name")
        )
        qty = sum(
            int(g.get("goods_number") or 0) for g in goods if isinstance(g, dict)
        )
        # Суммы PDD в фэнях (копейках): 98 → 0.98, 81480 → 814.80.
        amount = raw.get("order_amount")
        price = None
        if isinstance(amount, (int, float)):
            price = (Decimal(str(amount)) / 100).quantize(Decimal("0.01"))

        return {
            "external_order_id": sn,
            "product_title": title[:250],
            "price": price,
            "quantity": qty or 1,
            "status": status,
            "track_number": track,
            "raw": raw,
        }

    def _sync_parcel_for_order(self, order):
        """Создаёт посылку для заказа PDD — одна посылка на заказ (заказ = посылка).

        Идентификатор посылки — реальный трек-номер; пока его нет (заказ ждёт
        отправки) используем номер заказа (order_sn). Когда придёт реальный трек —
        он заменяет временный. Чужие посылки не трогаем."""
        from parcels.models import Parcel

        real_track = (order.track_number or "").strip()
        parcel_track = real_track or (order.external_order_id or "").strip()
        if not parcel_track:
            return None

        parcel = Parcel.objects.filter(order=order).first()
        if parcel is None:
            clash = Parcel.objects.filter(track_number=parcel_track).first()
            if clash:
                return clash if clash.order_id == order.id else None
            return Parcel.objects.create(
                order=order,
                user=order.user,
                cargo_id=order.user.cargo_id,
                client_code=order.user.client_code or "",
                track_number=parcel_track,
            )
        # Посылка уже есть: при появлении реального трека обновляем идентификатор.
        if (
            real_track
            and parcel.track_number != real_track
            and not Parcel.objects.filter(track_number=real_track).exclude(pk=parcel.pk).exists()
        ):
            parcel.track_number = real_track
            parcel.save(update_fields=("track_number", "updated_at"))
        return parcel

    def _apply_order(self, payload, *, result: SyncResult, create_parcels: bool):
        if not isinstance(payload, dict):
            result.errors.append("Пропуск: элемент заказа не является объектом")
            return
        # Достаём сырой заказ PDD: либо сам payload (order_sn в корне), либо
        # вложенный payload["raw"] (старое приложение шлёт нормализованный объект
        # с сырым заказом внутри). Так фильтр/цена/статус работают независимо от
        # версии приложения.
        pdd_raw = None
        if payload.get("order_sn"):
            pdd_raw = payload
        elif isinstance(payload.get("raw"), dict) and payload["raw"].get("order_sn"):
            pdd_raw = payload["raw"]
        if pdd_raw is not None:
            payload = self._normalize_pdd_order(pdd_raw)
            if payload is None:
                return  # отменён / не оплачен / не нужен — молча пропускаем
        external_id = (payload.get("external_order_id") or "").strip()
        if not external_id:
            result.errors.append("Пропуск: без external_order_id")
            return
        order, created = Order.objects.update_or_create(
            user=self.user,
            source=Order.Source.PINDUODUO,
            external_order_id=external_id,
            defaults=self._order_defaults(payload),
        )
        result.synced += 1
        if created:
            result.created += 1
        else:
            result.updated += 1
        if create_parcels:
            self._sync_parcel_for_order(order)

    @transaction.atomic
    def ingest_orders(self, orders, *, request=None, create_parcels: bool = True) -> SyncResult:
        """Сохраняет заказы (OrderPayload[]) и создаёт по ним посылки.

        Это путь B: заказы перехватываются приложением клиента из ответа
        order_list_v4 в WebView и присылаются сюда (логин/anti-content делает
        сама страница PDD, серверу подпись не нужна)."""
        result = SyncResult()
        if not isinstance(orders, list):
            return SyncResult(message="orders должен быть списком")
        for payload in orders:
            self._apply_order(payload, result=result, create_parcels=create_parcels)
        self.account.last_sync_at = timezone.now()
        self.account.last_sync_error = ""
        self.account.save(
            update_fields=("last_sync_at", "last_sync_error", "updated_at")
        )
        log_audit(
            AuditLog.Action.PINDUODUO_SYNCED,
            actor=self.user,
            target_user=self.user,
            metadata={"ingest": True, "synced": result.synced, "created": result.created},
            request=request,
        )
        if result.created > 0:
            notify(
                self.user,
                title="Новые заказы Pinduoduo",
                body=f"Добавлено новых заказов: {result.created}.",
                type=NotificationType.PINDUODUO_SYNCED,
                data={"created": result.created},
            )
        result.message = "ok"
        return result

    def mark_session_expired(self, *, request=None):
        """Помечает аккаунт как требующий повторного входа и уведомляет клиента."""
        self.account.is_connected = False
        self.account.last_sync_error = "Сессия Pinduoduo истекла"
        self.account.save(
            update_fields=("is_connected", "last_sync_error", "updated_at")
        )
        notify(
            self.user,
            title="Pinduoduo: войдите заново",
            body=(
                "Сессия Pinduoduo истекла. Откройте Pinduoduo в приложении и "
                "войдите снова, чтобы заказы продолжили синхронизироваться."
            ),
            type=NotificationType.SYSTEM,
            data={"reason": "session_expired"},
        )
        return self.account

    @transaction.atomic
    def sync_orders(self, *, request=None) -> SyncResult:
        if not self.account.is_connected:
            return SyncResult(message="Аккаунт Pinduoduo не подключён")

        result = SyncResult()
        try:
            payloads = list(self.client.fetch_orders(self.account.session_data or {}))
        except Exception as exc:
            self.account.last_sync_error = str(exc)[:500]
            self.account.save(update_fields=("last_sync_error", "updated_at"))
            logger.exception("Pinduoduo fetch_orders failed")
            return SyncResult(message="Ошибка получения заказов", errors=[str(exc)])

        for payload in payloads:
            self._apply_order(payload, result=result, create_parcels=True)

        self.account.last_sync_at = timezone.now()
        self.account.last_sync_error = ""
        self.account.save(
            update_fields=("last_sync_at", "last_sync_error", "updated_at")
        )
        log_audit(
            AuditLog.Action.PINDUODUO_SYNCED,
            actor=self.user,
            target_user=self.user,
            metadata={
                "synced": result.synced,
                "created": result.created,
                "updated": result.updated,
            },
            request=request,
        )
        if result.synced > 0:
            notify(
                self.user,
                title="Синхронизация Pinduoduo",
                body=(
                    f"Обновлено заказов: {result.synced}. "
                    f"Новых: {result.created}, изменено: {result.updated}."
                ),
                type=NotificationType.PINDUODUO_SYNCED,
                data={"synced": result.synced},
            )
        result.message = "ok"
        return result

    @transaction.atomic
    def ingest_webhook_payload(self, payload: dict, *, request=None) -> SyncResult:
        """Принимает массив заказов от внешнего сервера-парсера и сохраняет.

        Ожидаемый формат payload: {"orders": [OrderPayload, ...]}.
        Используется, когда Pinduoduo интегрирован через отдельный воркер,
        который шлёт нам заказы webhook'ом."""
        orders = payload.get("orders") or []
        result = SyncResult()
        if not isinstance(orders, list):
            return SyncResult(message="orders должен быть списком")

        for order_payload in orders:
            self._apply_order(order_payload, result=result, create_parcels=True)

        self.account.last_sync_at = timezone.now()
        self.account.save(update_fields=("last_sync_at", "updated_at"))
        log_audit(
            AuditLog.Action.PINDUODUO_SYNCED,
            actor=self.user,
            target_user=self.user,
            metadata={"webhook": True, "synced": result.synced},
            request=request,
        )
        return result
