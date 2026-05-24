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
            external_id = (payload.get("external_order_id") or "").strip()
            if not external_id:
                result.errors.append("Пропуск: без external_order_id")
                continue
            mapped_status = SOURCE_STATUS_MAP.get(
                (payload.get("status") or "").lower(), Order.Status.CREATED
            )
            defaults = {
                "user": self.user,
                "source": Order.Source.PINDUODUO,
                "product_url": payload.get("product_url", ""),
                "product_title": payload.get("product_title", ""),
                "price": _to_decimal(payload.get("price")),
                "quantity": int(payload.get("quantity") or 1),
                "status": mapped_status,
                "track_number": payload.get("track_number", ""),
                "raw_data": payload.get("raw") or {},
            }
            order, created = Order.objects.update_or_create(
                user=self.user,
                source=Order.Source.PINDUODUO,
                external_order_id=external_id,
                defaults=defaults,
            )
            if created:
                result.created += 1
            else:
                result.updated += 1
            result.synced += 1

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
            external_id = (order_payload.get("external_order_id") or "").strip()
            if not external_id:
                result.errors.append("Пропуск: без external_order_id")
                continue
            mapped_status = SOURCE_STATUS_MAP.get(
                (order_payload.get("status") or "").lower(), Order.Status.CREATED
            )
            defaults = {
                "user": self.user,
                "source": Order.Source.PINDUODUO,
                "product_url": order_payload.get("product_url", ""),
                "product_title": order_payload.get("product_title", ""),
                "price": _to_decimal(order_payload.get("price")),
                "quantity": int(order_payload.get("quantity") or 1),
                "status": mapped_status,
                "track_number": order_payload.get("track_number", ""),
                "raw_data": order_payload.get("raw") or {},
            }
            _, created = Order.objects.update_or_create(
                user=self.user,
                source=Order.Source.PINDUODUO,
                external_order_id=external_id,
                defaults=defaults,
            )
            result.synced += 1
            if created:
                result.created += 1
            else:
                result.updated += 1

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
