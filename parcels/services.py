import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Parcel

logger = logging.getLogger(__name__)


class ScanError(Exception):
    """Доменная ошибка сканирования (мапится на 4xx во view)."""

    def __init__(self, message, code="invalid"):
        super().__init__(message)
        self.message = message
        self.code = code


# Порядок статусов по маршруту (для защиты от отката при повторных сканах).
# Маршрут: Китай → обработка → Топа → в пути → Кыргызстан → ПВЗ.
# in_storage / sent_to_kyrgyzstan — устаревшие (не в авто-цепочке), оставлены
# для старых посылок и совместимости.
_STATUS_ORDER = [
    Parcel.Status.CREATED,
    Parcel.Status.PURCHASED,
    Parcel.Status.WAITING_CHINA_WAREHOUSE,
    Parcel.Status.ARRIVED_CHINA_WAREHOUSE,
    Parcel.Status.IN_STORAGE,
    Parcel.Status.SENT_TO_KYRGYZSTAN,
    Parcel.Status.PROCESSING,
    Parcel.Status.ARRIVED_TOPA,
    Parcel.Status.IN_TRANSIT,
    Parcel.Status.ARRIVED_KYRGYZSTAN,
    Parcel.Status.AT_PICKUP_POINT,
    Parcel.Status.CITY_DELIVERY,
    Parcel.Status.DELIVERED,
    Parcel.Status.ISSUED,
]
STATUS_RANK = {s: i for i, s in enumerate(_STATUS_ORDER)}
STATUS_RANK[Parcel.Status.CANCELLED] = 999


def calc_delivery_price(cargo, weight):
    """Стоимость доставки = вес × тариф карго (сом/кг). None если данных нет."""
    rate = getattr(cargo, "price_per_kg_kgs", None)
    if weight is None or not rate:
        return None
    return (Decimal(weight) * Decimal(rate)).quantize(Decimal("0.01"))


def resolve_pickup(pickup_point_id, user=None, actor=None):
    """ПВЗ приёмки при статусе «В ПВЗ».

    Привязанный к ПВЗ оператор физически принимает только в свой ПВЗ —
    переключатель ПВЗ на него не влияет (иначе посылка «уедет» в чужой ПВЗ
    и станет ему невидимой). Для остальных приоритет:
    явный ПВЗ (переключатель) → ПВЗ клиента → ПВЗ оператора.

    Возвращает объект ``PickupPoint`` (или ``None``).
    """
    from common.cargo_scoping import bound_pickup_id
    from pickup_points.models import PickupPoint

    if actor is not None:
        bound = bound_pickup_id(actor)
        if bound:
            return getattr(actor, "pickup_point", None) or PickupPoint.objects.filter(pk=bound).first()

    pp = None
    if pickup_point_id:
        pp = PickupPoint.objects.filter(pk=pickup_point_id).first()
    if pp is None and user is not None:
        pp = getattr(user, "pickup_point", None)
    if pp is None and actor is not None:
        pp = getattr(actor, "pickup_point", None)
    return pp


def resolve_pickup_address(pickup_point_id, user=None, actor=None):
    """Адрес ПВЗ (текст) — обёртка над :func:`resolve_pickup`."""
    pp = resolve_pickup(pickup_point_id, user=user, actor=actor)
    return pp.address if pp else None


@transaction.atomic
def scan_parcel(
    track_number,
    cargo,
    actor=None,
    status=None,
    weight=None,
    request=None,
    global_resolve=False,
    client_code=None,
    pickup_point=None,
):
    """Зарегистрировать посылку по трек-номеру (сканер, одно поле).

    Если передан ``weight`` — сохраняем вес и пересчитываем стоимость доставки
    по тарифу карго (``price_per_kg_kgs``).

    ``global_resolve=True`` — режим общего склада в Китае (оператор Китая один
    на все карго; ``cargo`` может быть ``None``). Карго определяется так:
      1) по заказу с этим треком среди всех карго;
      2) если заказа нет — по ``client_code`` (клиент заказал напрямую на наш
         адрес в Китае и подписал коробку своим кодом);
      3) иначе — отклоняем (карго определить нельзя).

    Возвращает кортеж ``(result, parcel)`` где ``result`` — одно из
    ``updated`` / ``created_from_order`` / ``created_manual`` / ``created_pending``.
    """
    from django.contrib.auth import get_user_model
    from orders.models import Order

    from common.audit import log_audit
    from common.models import AuditLog

    User = get_user_model()

    track_number = (track_number or "").strip()
    client_code = (client_code or "").strip()
    if not track_number:
        raise ScanError("track_number обязателен", code="invalid")
    if cargo is None and not global_resolve:
        raise ScanError("Не определён карго-центр", code="no_cargo")

    target_status = status or Parcel.Status.ARRIVED_CHINA_WAREHOUSE
    if target_status not in Parcel.Status.values:
        raise ScanError("Неизвестный статус", code="invalid")

    existing = Parcel.objects.select_related("user").filter(track_number=track_number).first()
    if existing is not None:
        if existing.cargo_id is None and not global_resolve and cargo is not None:
            # «Ничью» посылку (со склада в Китае) усыновляет карго оператора.
            existing.cargo = cargo
            existing.save(update_fields=["cargo", "updated_at"])
        elif not global_resolve and existing.cargo_id not in (None, cargo.id):
            raise ScanError(
                "Трек уже зарегистрирован в другом карго-центре", code="conflict"
            )

        # Защита от случайных повторных сканов: статус не откатывается назад.
        cur_rank = STATUS_RANK.get(existing.status, -1)
        tgt_rank = STATUS_RANK.get(target_status, -1)
        if target_status == existing.status:
            # Тот же статус — повторный скан, ничего не меняем.
            result = "unchanged"
        elif cur_rank >= 0 and tgt_rank >= 0 and tgt_rank < cur_rank:
            raise ScanError(
                f"Посылка уже дальше по маршруту: «{existing.get_status_display()}». "
                "Повторный скан отклонён.",
                code="already_advanced",
            )
        else:
            update_parcel_status(existing, target_status, changed_by=actor)
            result = "updated"

        # Приёмка в ПВЗ: фиксируем/уточняем физический ПВЗ и адрес — в т.ч. при
        # повторном скане (сканирует оператор → посылка физически у него).
        if target_status == Parcel.Status.AT_PICKUP_POINT:
            pp = resolve_pickup(pickup_point, user=existing.user, actor=actor)
            if pp is not None and existing.pickup_point_id != pp.id:
                existing.pickup_point = pp
                existing.location = pp.address
                existing.save(update_fields=["pickup_point", "location", "updated_at"])

        # Вес/стоимость можно уточнить и при повторном скане того же статуса.
        if weight is not None:
            existing.weight = weight
            existing.delivery_price = calc_delivery_price(existing.cargo, weight)
            existing.save(update_fields=["weight", "delivery_price", "updated_at"])
        parcel = existing
    else:
        order_qs = Order.objects.select_related("user", "user__cargo").filter(
            track_number=track_number
        )
        if not global_resolve:
            order_qs = order_qs.filter(user__cargo_id=cargo.id)
        order = order_qs.first()

        user = None
        if order is not None:
            user = order.user
            if global_resolve:
                cargo = order.user.cargo
        elif client_code:
            # Ручной приём: клиент заказал напрямую и подписал коробку кодом.
            candidates = User.objects.select_related("cargo").filter(
                client_code=client_code
            )
            if not global_resolve and cargo is not None:
                candidates = candidates.filter(cargo_id=cargo.id)
            matches = list(candidates[:2])
            if len(matches) > 1:
                raise ScanError(
                    "Код клиента найден в нескольких карго — уточните карго",
                    code="ambiguous",
                )
            if not matches:
                raise ScanError(
                    f"Клиент с кодом {client_code} не найден", code="no_client"
                )
            user = matches[0]
            cargo = user.cargo
        # Иначе (общий склад без заказа и кода) — «ничья» посылка: cargo=None,
        # карго/клиент присвоятся позже (при совпадении заказа или приёмке в карго).

        location = ""
        received_pickup = None
        if target_status == Parcel.Status.AT_PICKUP_POINT:
            received_pickup = resolve_pickup(pickup_point, user=user, actor=actor)
            location = received_pickup.address if received_pickup else ""

        parcel = Parcel(
            cargo=cargo,
            user=user,
            order=order,
            pickup_point=received_pickup,
            track_number=track_number,
            client_code=(user.client_code if user else client_code) or "",
            status=target_status,
            location=location,
            weight=weight,
            delivery_price=calc_delivery_price(cargo, weight),
        )
        parcel.apply_status_timestamps()
        parcel._status_changed_by = actor
        parcel.save()
        result = "created_from_order" if order else ("created_manual" if user else "created_pending")

    log_audit(
        AuditLog.Action.PARCEL_SCANNED,
        actor=actor,
        target_user=parcel.user,
        description=f"Сканирование трека {track_number}: {result}",
        metadata={"track_number": track_number, "result": result, "parcel_id": parcel.id},
        request=request,
    )
    logger.info("Parcel scanned", extra={"track_number": track_number, "result": result})
    return result, parcel


def update_parcel_status(parcel, status, comment=None, changed_by=None):
    if status not in Parcel.Status.values:
        raise ValueError("Invalid parcel status")
    parcel._status_comment = comment or ""
    parcel._status_changed_by = changed_by
    parcel.status = status
    fields = ["status", "updated_at"]
    # Выдан клиенту → в архив (и клиенту, и карго).
    if status == Parcel.Status.ISSUED and not parcel.is_archived:
        parcel.is_archived = True
        fields.append("is_archived")
    extra_fields = parcel.apply_status_timestamps()
    parcel.save(update_fields=[*fields, *extra_fields])
    logger.info(
        "Parcel status updated",
        extra={"parcel_id": parcel.id, "track_number": parcel.track_number, "status": status},
    )
    return parcel


# Порядок авто-цепочки после 1-го скана (скан на складе в Китае).
# Китай → обработка → Топа → в пути → Кыргызстан. Последний статус —
# «ожидание 2-го скана в ПВЗ» (дальше at_pickup_point ставится вручную).
AUTO_FLOW = [
    Parcel.Status.ARRIVED_CHINA_WAREHOUSE,
    Parcel.Status.PROCESSING,
    Parcel.Status.ARRIVED_TOPA,
    Parcel.Status.IN_TRANSIT,
    Parcel.Status.ARRIVED_KYRGYZSTAN,
]


def _auto_anchor(parcel):
    """Момент начала авто-цепочки — когда посылка попала на склад в Китае."""
    from .models import ParcelStatusHistory

    started = (
        ParcelStatusHistory.objects.filter(
            parcel=parcel, status=Parcel.Status.ARRIVED_CHINA_WAREHOUSE
        )
        .order_by("created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    return started or parcel.arrived_at or parcel.created_at


def advance_parcel_auto(parcel, now=None):
    """Продвинуть посылку по авто-цепочке в зависимости от прошедшего времени.

    Идемпотентно и «догоняет» несколько шагов сразу (если крон долго не
    запускался). Возвращает True, если статус изменился.
    """
    now = now or timezone.now()
    if parcel.is_archived or parcel.status not in AUTO_FLOW:
        return False
    idx = AUTO_FLOW.index(parcel.status)
    if idx >= len(AUTO_FLOW) - 1:
        return False  # ARRIVED_KYRGYZSTAN — ждём скан в ПВЗ

    delays = settings.AUTO_STATUS_DELAYS
    anchor = _auto_anchor(parcel)
    target = idx
    threshold = anchor
    for i in range(len(AUTO_FLOW) - 1):
        step = delays.get(AUTO_FLOW[i])
        if step is None:
            break
        threshold = threshold + timedelta(seconds=step)
        if threshold <= now:
            target = i + 1
        else:
            break

    if target <= idx:
        return False
    while idx < target:
        idx += 1
        # Уведомляем только по итоговому статусу прогона: посылка может
        # «догнать» несколько шагов сразу (крон долго не запускался, старая
        # посылка), и четыре пуша подряд были бы спамом. Промежуточные шаги
        # всё равно попадают в историю и видны в трекинге.
        parcel._suppress_notification = idx < target
        update_parcel_status(parcel, AUTO_FLOW[idx], comment="Автоматический статус")
    return True


def advance_all_parcels(now=None):
    """Продвинуть все посылки в авто-цепочке. Возвращает число сдвинутых.

    Общая логика для management-команды ``advance_parcels`` и Celery-задачи.
    """
    advancing = list(AUTO_FLOW[:-1])
    moved = 0
    qs = Parcel.objects.filter(status__in=advancing, is_archived=False)
    for parcel in qs.iterator():
        if advance_parcel_auto(parcel, now=now):
            moved += 1
    return moved
