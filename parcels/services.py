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
    # Порядок маршрута: со склада посылка сначала едет («В пути») и только
    # потом попадает в Топа. Ранг участвует в защите от отката при повторном
    # скане, поэтому обязан совпадать с AUTO_FLOW.
    Parcel.Status.IN_TRANSIT,
    Parcel.Status.ARRIVED_TOPA,
    Parcel.Status.ARRIVED_KYRGYZSTAN,
    # Последний авто-статус. Дальше — только реальный скан в ПВЗ, поэтому
    # ранг обязан быть ниже AT_PICKUP_POINT, иначе скан сочтут откатом.
    Parcel.Status.CUSTOMS,
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
def _resolve_client_by_code(client_code, cargo, global_resolve):
    """Клиент по коду с коробки. Код уникален только внутри карго.

    Общий для приёма новой посылки и для приёма уже существующей ничьей: раньше
    код разбирался только при создании, и у посылки, принятой в Китае без
    клиента, введённый в ПВЗ код молча терялся.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    candidates = User.objects.select_related("cargo").filter(client_code=client_code)
    if not global_resolve and cargo is not None:
        candidates = candidates.filter(cargo_id=cargo.id)
    matches = list(candidates[:2])
    if len(matches) > 1:
        raise ScanError(
            "Код клиента найден в нескольких карго — уточните карго",
            code="ambiguous",
        )
    if not matches:
        raise ScanError(f"Клиент с кодом {client_code} не найден", code="no_client")
    return matches[0]


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

        # Хозяина разбираем до любых изменений: опечатка в коде или чужая
        # коробка не должны полуприменить скан (статус сменился, а клиент нет).
        new_owner = None
        new_order = None
        placeholders = []
        if existing.user_id is None:
            if client_code:
                # Посылку приняли в Китае без клиента, а в ПВЗ ввели код. Раньше
                # он здесь молча выбрасывался.
                new_owner = _resolve_client_by_code(client_code, cargo, global_resolve)
            else:
                # Заказ мог прийти уже после скана в Китае — подбираем по нему.
                order_qs = Order.objects.select_related("user").filter(
                    track_number=track_number, user__isnull=False
                )
                if not global_resolve and cargo is not None:
                    order_qs = order_qs.filter(user__cargo_id=cargo.id)
                candidate = order_qs.first()
                if candidate is not None:
                    # Тот же план, что у синхронизации и подтяжки: заглушка
                    # уступает место, настоящая посылка у заказа — конфликт.
                    plan, placeholders = plan_order_attach(existing, candidate)
                    if plan != "conflict":
                        new_order = candidate
                        new_owner = candidate.user
        elif client_code and existing.user.client_code and client_code != existing.user.client_code:
            # Другой код на посылке с хозяином — перепутанная коробка или
            # наклейка. Молча переписать хозяина — значит отдать чужую посылку.
            raise ScanError(
                f"Посылка уже привязана к клиенту {existing.user.client_code}, "
                f"а введён код {client_code}. Проверьте коробку.",
                code="client_mismatch",
            )

        # Защита от случайных повторных сканов: статус не откатывается назад.
        cur_rank = STATUS_RANK.get(existing.status, -1)
        tgt_rank = STATUS_RANK.get(target_status, -1)
        if (
            target_status != existing.status
            and cur_rank >= 0
            and tgt_rank >= 0
            and tgt_rank < cur_rank
        ):
            raise ScanError(
                f"Посылка уже дальше по маршруту: «{existing.get_status_display()}». "
                "Повторный скан отклонён.",
                code="already_advanced",
            )

        # Хозяина ставим ДО смены статуса: сигнал смены отправит «Посылка в
        # ПВЗ» уже ему, а не в пустоту.
        if new_owner is not None:
            for placeholder in placeholders:
                retire_placeholder(placeholder, replaced_by=existing)
            existing.user = new_owner
            existing.client_code = new_owner.client_code or ""
            fields = ["user", "client_code", "updated_at"]
            if new_order is not None:
                existing.order = new_order
                fields.append("order")
            if existing.cargo_id is None:
                existing.cargo_id = new_owner.cargo_id
                fields.append("cargo")
            existing.save(update_fields=fields)

        if target_status == existing.status:
            if new_owner is not None:
                # Статус тот же, но клиент присвоен — это изменение, и
                # «unchanged» соврал бы. Сигнал смены статуса не сработает,
                # поэтому о посылке клиенту сообщаем сами.
                from .signals import send_parcel_status_notification

                send_parcel_status_notification(existing)
                result = "updated"
            else:
                # Тот же статус — повторный скан, ничего не меняем.
                result = "unchanged"
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
            user = _resolve_client_by_code(client_code, cargo, global_resolve)
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


# Порядок авто-цепочки после 1-го скана (скан на складе в Китае):
# Китай → классификация → в пути → Топа → Кыргызстан. Последний статус —
# «ожидание 2-го скана в ПВЗ» (дальше at_pickup_point ставится вручную).
# Таймерная часть маршрута: склад в Китае → (1 день) В пути → (7 дней) Таможня.
#
# Дальше цепочка молчит. Прибытие в Кыргызстан и в ПВЗ — физические факты, и
# раньше их объявлял таймер: посылка получала «Прибыл в Кыргызстан» на 9-й день
# независимо от того, где она была. По проду это давало разброс в обе стороны —
# часть партий доезжала за 3–5 дней и лежала в ПВЗ со статусом «в пути», а
# большинство ехало 10–14 дней, и клиент получал пуш о прибытии, пока фура была
# в дороге. Поэтому финальные статусы ставит только скан.
AUTO_FLOW = [
    Parcel.Status.ARRIVED_CHINA_WAREHOUSE,
    Parcel.Status.IN_TRANSIT,
    Parcel.Status.CUSTOMS,
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


def advance_parcel_auto(parcel, now=None, notify=True):
    """Продвинуть посылку по авто-цепочке в зависимости от прошедшего времени.

    Идемпотентно и «догоняет» несколько шагов сразу (если крон долго не
    запускался). Возвращает True, если статус изменился.

    ``notify=False`` гасит уведомления полностью — для разовой подтяжки после
    смены сроков: там сдвиг статусов вызван правкой настроек, а не реальным
    движением посылок, и пуш клиенту был бы ложным.
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
        parcel._suppress_notification = (not notify) or idx < target
        update_parcel_status(parcel, AUTO_FLOW[idx], comment="Автоматический статус")
    return True


def advance_all_parcels(now=None, notify=True):
    """Продвинуть все посылки в авто-цепочке. Возвращает число сдвинутых.

    Общая логика для management-команды ``advance_parcels`` и Celery-задачи.
    """
    advancing = list(AUTO_FLOW[:-1])
    moved = 0
    qs = Parcel.objects.filter(status__in=advancing, is_archived=False)
    for parcel in qs.iterator():
        if advance_parcel_auto(parcel, now=now, notify=notify):
            moved += 1
    return moved


# --- Импорт накладной файлом ---

# Предпросмотр: по первым строкам оператор видит, ту ли колонку мы взяли.
IMPORT_PREVIEW_LIMIT = 10


class ImportOutcome:
    """Итог разбора накладной.

    Инвариант: created + updated + skipped + len(errors) == total_rows.
    Если сумма не сходится, оператор не понимает, что случилось с остатком, —
    поэтому строка попадает ровно в одну корзину.
    """

    def __init__(self, total_rows=0):
        self.total_rows = total_rows
        self.created = 0
        self.updated = 0
        self.skipped = 0
        self.errors = []
        self.preview = []
        # Чьи строки истории пометить ссылкой на файл накладной.
        self.parcel_ids = []

    def as_dict(self):
        return {
            "total_rows": self.total_rows,
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "errors": self.errors,
        }


def apply_import_rows(
    items,
    *,
    cargo,
    actor=None,
    status=None,
    pickup_point=None,
    request=None,
    global_resolve=False,
):
    """Применить разобранные строки накладной. Семантика строки — как у scan/.

    Каждая строка в своей транзакции: одна плохая не должна отменить накладную.
    Неизвестный код клиента ``scan_parcel`` отклоняет (а не создаёт посылку без
    привязки) — здесь поведение то же, чтобы импорт и ручной скан не расходились.
    """
    from .importers import ImportFormatError, parse_weight

    outcome = ImportOutcome(total_rows=len(items))

    for item in items:
        if len(outcome.preview) < IMPORT_PREVIEW_LIMIT:
            outcome.preview.append(
                {
                    "row": item.row,
                    "track_number": item.track_number,
                    "weight": item.weight,
                    "client_code": item.client_code,
                }
            )

        track = (item.track_number or "").strip()
        if not track:
            # Хвост файла или строка-разделитель — не ошибка.
            outcome.skipped += 1
            continue

        try:
            weight = parse_weight(item.weight)
        except ImportFormatError as exc:
            outcome.errors.append(
                {"row": item.row, "track_number": track, "error": str(exc)}
            )
            continue

        try:
            with transaction.atomic():
                result, parcel = scan_parcel(
                    track,
                    cargo=cargo,
                    actor=actor,
                    status=status,
                    weight=weight,
                    client_code=(item.client_code or "").strip() or None,
                    pickup_point=pickup_point,
                    request=request,
                    global_resolve=global_resolve,
                )
                outcome.parcel_ids.append(parcel.id)
        except ScanError as exc:
            outcome.errors.append(
                {"row": item.row, "track_number": track, "error": exc.message}
            )
            continue
        except Exception as exc:  # неожиданная ошибка не должна рвать накладную
            logger.exception("Import row failed", extra={"track_number": track})
            outcome.errors.append(
                {"row": item.row, "track_number": track, "error": str(exc)}
            )
            continue

        if result in ("updated", "unchanged"):
            outcome.updated += 1
        else:
            outcome.created += 1

    return outcome


def adopt_pending_parcel(parcel, order, notify=True):
    """Привязать «ничью» посылку к заказу и его клиенту.

    Ничья посылка появляется, когда оператор на складе в Китае сканирует коробку
    раньше, чем заказ приедет с маркетплейса: на момент скана заказа нет, и
    ``scan_parcel`` честно оставляет ``created_pending``. Раньше никто её потом
    не подбирал — из этого росли жалобы «код клиента не присваивается»,
    «уведомления не приходят» и «клиент не видит товар по треку».

    Вызывать только для посылки без хозяина: проверку делает вызывающий, потому
    что перехват посылки чужого клиента — худшее, что тут может случиться.

    ``notify=False`` — для разовой подтяжки накопленного: там сотни посылок, и
    пачка уведомлений разом читалась бы как сбой.
    """
    from common.audit import log_audit
    from common.models import AuditLog

    client = order.user
    parcel.order = order
    parcel.user = client
    parcel.client_code = client.client_code or ""
    if parcel.cargo_id is None:
        parcel.cargo_id = client.cargo_id
    parcel.save(
        update_fields=["order", "user", "client_code", "cargo", "updated_at"]
    )

    if notify:
        from .signals import send_parcel_status_notification

        send_parcel_status_notification(parcel)

    log_audit(
        AuditLog.Action.PARCEL_SCANNED,
        target_user=client,
        description=f"Ничья посылка {parcel.track_number} привязана к заказу",
        metadata={
            "track_number": parcel.track_number,
            "result": "adopted_by_order",
            "parcel_id": parcel.id,
            "order_id": order.id,
        },
    )
    logger.info(
        "Pending parcel adopted",
        extra={"track_number": parcel.track_number, "order_id": order.id},
    )
    return parcel


# --- Одна физическая коробка — одна посылка у заказа ---


def _is_placeholder(parcel, order):
    """Заглушка: синхронизация завела посылку, пока у заказа не было трека.

    Узнаём её по треку, равному номеру заказа. Это не коробка, а место под неё.
    """
    external = (order.external_order_id or "").strip()
    return bool(external) and parcel.track_number == external


def plan_order_attach(parcel, order):
    """Можно ли привязать физическую посылку к заказу, не задвоив его.

    Возвращает (план, заглушки):
      «adopt»    — у заказа посылок нет, просто привязываем;
      «merge»    — у заказа только заглушки: они уступают место физической;
      «conflict» — у заказа уже есть посылка с настоящим треком, либо заглушку
                   успели выдать — привязывать нельзя, иначе у заказа станет
                   две посылки и клиент будет получать напоминания по лишней.
    Ничего не меняет — так скан может решить до любых изменений.
    """
    siblings = list(Parcel.objects.filter(order=order).exclude(pk=parcel.pk))
    if not siblings:
        return "adopt", []
    for sibling in siblings:
        if not _is_placeholder(sibling, order):
            return "conflict", []
        if sibling.is_archived or sibling.status == Parcel.Status.ISSUED:
            # Под этой заглушкой уже выдали коробку — её не трогаем.
            return "conflict", []
    return "merge", siblings


def retire_placeholder(placeholder, replaced_by):
    """Заглушка уступает место физической посылке: отменяем молча и в архив.

    Молча — потому что пуш «посылка отменена» про то, что было лишь местом под
    коробку, напугал бы клиента зря. Запись остаётся в базе для истории.
    """
    placeholder._suppress_notification = True
    update_parcel_status(
        placeholder,
        Parcel.Status.CANCELLED,
        comment=(
            f"Дубль: вместо трека стоял номер заказа. Заменена посылкой "
            f"{replaced_by.track_number}"
        ),
    )
    placeholder.is_archived = True
    placeholder.save(update_fields=["is_archived", "updated_at"])
    logger.info(
        "Placeholder parcel retired",
        extra={"placeholder": placeholder.track_number, "replaced_by": replaced_by.track_number},
    )


def attach_parcel_to_order(parcel, order, notify=True):
    """Привязать ничью физическую посылку к заказу по единому правилу.

    Одно правило на все пути — синхронизацию заказа, скан и подтяжку. Подбор
    01.10 шёл в обход него и задвоил 10 заказов: у каждого осталась заглушка и
    добавилась реальная посылка.

    Возвращает итог: «adopted», «merged» или «conflict» (ничего не сделано).
    """
    plan, placeholders = plan_order_attach(parcel, order)
    if plan == "conflict":
        return "conflict"
    for placeholder in placeholders:
        retire_placeholder(placeholder, replaced_by=parcel)
    adopt_pending_parcel(parcel, order, notify=notify)
    return "merged" if placeholders else "adopted"
