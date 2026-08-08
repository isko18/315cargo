"""Синхронизация заказов маркетплейсов (Pinduoduo, Taobao, …).

Один сервис на все маркетплейсы: различия вынесены в ``integrations.marketplaces``
(источник заказа, названия событий, разбор сырого ответа). Логика импорта,
дедупликации и создания посылок общая — она от маркетплейса не зависит.

Парсинг веб-страниц здесь намеренно не делается: сырые ответы списка заказов
перехватывает WebView мобильного приложения и присылает в ``/ingest/``.
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
from integrations.marketplaces import PINDUODUO, TAOBAO, get_marketplace
from integrations.models import MarketplaceAccount
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


class MarketplaceClient(Protocol):
    def fetch_orders(self, session_data: dict) -> Iterable[dict]: ...


class NullMarketplaceClient:
    """Клиент по умолчанию: серверных запросов к маркетплейсу не делаем.

    Заказы приходят из WebView приложения через ``/ingest/``. Серверный
    «доступ по сессии клиента» здесь сознательно не реализован: запрос с
    датацентрового IP по кукам клиента — прямой путь к бану аккаунта.
    """

    def fetch_orders(self, session_data: dict) -> Iterable[dict]:
        return []


def get_default_client(marketplace: str) -> MarketplaceClient:
    setting = {
        PINDUODUO: "PINDUODUO_CLIENT_PATH",
        TAOBAO: "TAOBAO_CLIENT_PATH",
    }.get(marketplace, "")
    path = (getattr(settings, setting, "") or "") if setting else ""
    if not path:
        return NullMarketplaceClient()
    try:
        module_name, attr_name = path.rsplit(".", 1)
        from importlib import import_module

        module = import_module(module_name)
        client_cls = getattr(module, attr_name)
        return client_cls()
    except Exception:
        logger.exception("Не удалось загрузить клиент %s, работаем без него", path)
        return NullMarketplaceClient()


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


class MarketplaceSyncService:
    """Импорт заказов одного клиента с одного маркетплейса."""

    marketplace_key = PINDUODUO

    def __init__(self, user, client: MarketplaceClient | None = None, marketplace: str | None = None):
        self.user = user
        self.marketplace = get_marketplace(marketplace or self.marketplace_key)
        self.account, _ = MarketplaceAccount.objects.get_or_create(
            user=user, marketplace=self.marketplace.key
        )
        self.client = client or get_default_client(self.marketplace.key)

    # --- состояние подключения ---

    def connect(self, session_data: dict | None = None, *, request=None):
        self.account.is_connected = True
        if not self.account.external_user_id:
            self.account.external_user_id = (session_data or {}).get(
                "external_user_id", f"{self.marketplace.key}-{self.user.id}"
            )
        self.account.session_data = session_data or {}
        self.account.last_sync_error = ""
        # Точка отсчёта жизни сессии: по ней считаем, сколько она продержалась.
        self.account.session_started_at = timezone.now()
        self.account.session_expired_at = None
        self.account.last_expire_reason = ""
        self.account.save(
            update_fields=(
                "is_connected",
                "external_user_id",
                "session_data",
                "last_sync_error",
                "session_started_at",
                "session_expired_at",
                "last_expire_reason",
                "updated_at",
            )
        )
        log_audit(
            self.marketplace.audit_connected,
            actor=self.user,
            target_user=self.user,
            request=request,
        )
        notify(
            self.user,
            title=f"{self.marketplace.title} подключён",
            body=(
                f"Ваш аккаунт {self.marketplace.title} успешно подключён. "
                "Заказы будут синхронизироваться автоматически."
            ),
            type=self.marketplace.notify_connected,
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
            self.marketplace.audit_disconnected,
            actor=self.user,
            target_user=self.user,
            request=request,
        )
        return self.account

    def mark_session_expired(self, *, reason: str = "", request=None):
        """Помечает аккаунт как требующий повторного входа и уведомляет клиента.

        Пишем момент и причину: сессия живёт в WebView приложения, и без этих
        отметок нельзя отличить «клиент открыл официальное приложение» от
        «куки не пережили перезапуск» или «аккаунт забанили».
        """
        now = timezone.now()
        started = self.account.session_started_at
        lifetime_min = round((now - started).total_seconds() / 60, 1) if started else None

        self.account.is_connected = False
        self.account.last_sync_error = f"Сессия {self.marketplace.title} истекла"
        self.account.session_expired_at = now
        self.account.last_expire_reason = (reason or "")[:64]
        self.account.save(
            update_fields=(
                "is_connected",
                "last_sync_error",
                "session_expired_at",
                "last_expire_reason",
                "updated_at",
            )
        )
        log_audit(
            self.marketplace.audit_session_expired,
            actor=self.user,
            target_user=self.user,
            description=f"Сессия прожила {lifetime_min} мин" if lifetime_min is not None else "",
            metadata={"reason": reason or "unknown", "lifetime_minutes": lifetime_min},
            request=request,
        )
        notify(
            self.user,
            title=f"{self.marketplace.title}: войдите заново",
            body=(
                f"Сессия {self.marketplace.title} истекла. Откройте "
                f"{self.marketplace.title} в приложении и войдите снова, чтобы "
                "заказы продолжили синхронизироваться."
            ),
            type=NotificationType.SYSTEM,
            data={"reason": "session_expired", "marketplace": self.marketplace.key},
        )
        return self.account

    # --- общий маппинг и сохранение заказов ---

    def _order_defaults(self, payload: dict) -> dict:
        mapped_status = SOURCE_STATUS_MAP.get(
            (payload.get("status") or "").lower(), Order.Status.CREATED
        )
        return {
            "user": self.user,
            "source": self.marketplace.source,
            "product_url": payload.get("product_url", ""),
            "product_title": payload.get("product_title", ""),
            "price": _to_decimal(payload.get("price")),
            "quantity": int(payload.get("quantity") or 1),
            "status": mapped_status,
            "track_number": (payload.get("track_number") or "").strip(),
            "raw_data": payload.get("raw") or {},
        }

    def _sync_parcel_for_order(self, order):
        """Одна посылка на заказ.

        Идентификатор посылки — реальный трек-номер; пока его нет (заказ ждёт
        отправки) используем номер заказа. Когда придёт реальный трек — он
        заменяет временный. Чужие посылки не трогаем.
        """
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
        # Сырой заказ маркетплейса приходит либо сам по себе, либо вложенным в
        # payload["raw"] (старые версии приложения шлют нормализованный объект).
        # Так разбор работает независимо от версии приложения.
        raw = None
        if self.marketplace.is_raw(payload):
            raw = payload
        elif isinstance(payload.get("raw"), dict) and self.marketplace.is_raw(payload["raw"]):
            raw = payload["raw"]
        if raw is not None:
            payload = self.marketplace.normalize(raw)
            if payload is None:
                return  # отменён / не оплачен / не нужен — молча пропускаем
        external_id = (payload.get("external_order_id") or "").strip()
        if not external_id:
            result.errors.append("Пропуск: без external_order_id")
            return
        order, created = Order.objects.update_or_create(
            user=self.user,
            source=self.marketplace.source,
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

    def _expand(self, orders):
        """Развернуть полный ответ маркетплейса в список заказов.

        Мобилка может прислать как готовый список, так и весь ответ целиком —
        у Taobao заказы вообще лежат деревом компонентов, вытащить их можно
        только из ответа целиком.
        """
        extract = self.marketplace.extract
        if not extract:
            return list(orders)
        expanded = []
        for payload in orders:
            if not isinstance(payload, dict):
                expanded.append(payload)
                continue
            if self.marketplace.is_raw(payload):
                expanded.append(payload)  # уже собранный заказ
                continue
            found = extract(payload)
            expanded.extend(found if found else [payload])
        return expanded

    @transaction.atomic
    def ingest_orders(self, orders, *, request=None, create_parcels: bool = True) -> SyncResult:
        """Сохраняет заказы из WebView и создаёт по ним посылки."""
        result = SyncResult()
        for payload in self._expand(orders):
            self._apply_order(payload, result=result, create_parcels=create_parcels)
        self.account.last_sync_at = timezone.now()
        self.account.last_sync_error = ""
        self.account.save(
            update_fields=("last_sync_at", "last_sync_error", "updated_at")
        )
        log_audit(
            self.marketplace.audit_synced,
            actor=self.user,
            target_user=self.user,
            metadata={"ingest": True, "synced": result.synced, "created": result.created},
            request=request,
        )
        if result.created > 0:
            notify(
                self.user,
                title=f"Новые заказы {self.marketplace.title}",
                body=f"Добавлено новых заказов: {result.created}.",
                type=self.marketplace.notify_synced,
                data={"created": result.created, "marketplace": self.marketplace.key},
            )
        result.message = "ok"
        return result

    def ingest_webhook_payload(self, payload: dict, *, request=None) -> SyncResult:
        """Заказы от внешнего сервера-парсера (админский вебхук)."""
        return self.ingest_orders(
            payload.get("orders") or [], request=request, create_parcels=True
        )

    @transaction.atomic
    def sync_orders(self, *, request=None) -> SyncResult:
        if not self.account.is_connected:
            return SyncResult(message=f"Аккаунт {self.marketplace.title} не подключён")

        result = SyncResult()
        try:
            payloads = list(self.client.fetch_orders(self.account.session_data or {}))
        except Exception as exc:
            self.account.last_sync_error = str(exc)[:500]
            self.account.save(update_fields=("last_sync_error", "updated_at"))
            logger.exception("%s fetch_orders failed", self.marketplace.title)
            return SyncResult(message="Ошибка получения заказов", errors=[str(exc)])

        for payload in payloads:
            self._apply_order(payload, result=result, create_parcels=True)

        self.account.last_sync_at = timezone.now()
        self.account.last_sync_error = ""
        self.account.save(
            update_fields=("last_sync_at", "last_sync_error", "updated_at")
        )
        log_audit(
            self.marketplace.audit_synced,
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
                title=f"Синхронизация {self.marketplace.title}",
                body=(
                    f"Обновлено заказов: {result.synced}. "
                    f"Новых: {result.created}, изменено: {result.updated}."
                ),
                type=self.marketplace.notify_synced,
                data={"synced": result.synced, "marketplace": self.marketplace.key},
            )
        result.message = "ok"
        return result


class PinduoduoSyncService(MarketplaceSyncService):
    marketplace_key = PINDUODUO


class TaobaoSyncService(MarketplaceSyncService):
    marketplace_key = TAOBAO
