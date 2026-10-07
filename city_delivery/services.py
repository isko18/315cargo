import re
from collections import Counter
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import CityDeliveryRequest, CityDeliveryTariff

Status = CityDeliveryRequest.Status

# Живая заявка — ещё не доставлена и не отменена. У клиента такая одна.
CLOSED_STATUSES = (Status.DELIVERED, Status.CANCELLED)
# Менять точку, получателя и состав можно, пока курьер не взял заявку в работу.
EDITABLE_STATUSES = (Status.CREATED, Status.PRICE_CALCULATED, Status.ACCEPTED)

ZERO = Decimal("0.00")

# Поля, которые клиент заполняет сам. Повторный POST — полная анкета:
# чего в ней нет, то очищается; PATCH трогает только присланное.
_TEXT_FIELDS = ("address", "comment", "delivery_time_slot", "suggested_point")
_CLIENT_FIELDS = (
    "delivery_point",
    "suggested_point",
    "address",
    "recipient_name",
    "recipient_phone",
    "comment",
    "delivery_date",
    "delivery_time_slot",
)


class DeliveryInProgress(Exception):
    """Курьер уже взял заявку — менять её поздно."""

    def __init__(self, request):
        super().__init__(request.pk)
        self.request = request


def resolve_tariff_for_user(user) -> CityDeliveryTariff | None:
    pickup_point_id = getattr(user, "pickup_point_id", None)
    if pickup_point_id:
        tariff = (
            CityDeliveryTariff.objects.filter(
                is_active=True, pickup_point_id=pickup_point_id
            )
            .order_by("-is_default", "title")
            .first()
        )
        if tariff:
            return tariff
    # Fallback to a general tariff (no specific pickup point). A tariff bound to
    # a cargo applies only to that cargo's clients, so one cargo's tariff can
    # never price another's parcels. A cargo-agnostic tariff (cargo IS NULL) is
    # a true global default usable by everyone, and a cargo-specific tariff
    # takes precedence over the global one.
    fallback = CityDeliveryTariff.objects.filter(
        is_active=True, pickup_point__isnull=True
    )
    cargo_id = getattr(user, "cargo_id", None)
    if cargo_id:
        specific = (
            fallback.filter(cargo_id=cargo_id).order_by("-is_default", "title").first()
        )
        if specific:
            return specific
    return fallback.filter(cargo__isnull=True).order_by("-is_default", "title").first()


def resolve_tariff(parcel) -> CityDeliveryTariff | None:
    return resolve_tariff_for_user(parcel.user)


def calculate_price(parcel, tariff: CityDeliveryTariff | None = None):
    tariff = tariff or resolve_tariff(parcel)
    if not tariff:
        return None, None
    price = tariff.calculate(weight_kg=parcel.weight or 0)
    return price, tariff


def price_for(user, parcels):
    """Цена заявки целиком: тариф по суммарному весу, а без тарифа — 0.

    Доставка по городу бесплатная: тарифов нет — значит 0, а не «будет
    рассчитана». Карго, которому нужна платная, заводит свой тариф в панели.
    """
    tariff = resolve_tariff_for_user(user)
    if tariff is None:
        return ZERO, None
    total = sum((p.weight or Decimal("0")) for p in parcels)
    return tariff.calculate(weight_kg=total).quantize(Decimal("0.01")), tariff


def live_request_for(user):
    """Живая заявка клиента — самая свежая, если от старой схемы их несколько."""
    return (
        CityDeliveryRequest.objects.filter(user=user)
        .exclude(status__in=CLOSED_STATUSES)
        .order_by("-created_at")
        .first()
    )


def _live_requests_of(user_id):
    return CityDeliveryRequest.objects.filter(user_id=user_id).exclude(
        status__in=CLOSED_STATUSES
    )


def waiting_parcels(user_id, exclude_request_id=None):
    """Посылки клиента в ПВЗ, которые ещё ни в какой живой заявке."""
    from parcels.models import Parcel

    busy = _live_requests_of(user_id)
    if exclude_request_id:
        busy = busy.exclude(pk=exclude_request_id)
    return list(
        Parcel.objects.filter(
            user_id=user_id, status=Parcel.Status.AT_PICKUP_POINT, is_archived=False
        )
        .exclude(city_deliveries__in=busy)
        .exclude(city_delivery_requests__in=busy)
        .distinct()
        .order_by("id")
    )


def _apply_parcels(request, parcels):
    """Цена, тариф, статус и старое parcel — всё, что следует из состава.

    Старое parcel держим равным первой посылке: по нему установленные версии
    приложения показывают трек в заявке.
    """
    parcels = sorted(parcels, key=lambda p: p.id)
    price, tariff = price_for(request.user, parcels)
    request.price = price
    request.tariff = tariff
    request.parcel = parcels[0] if parcels else None
    if request.status in (Status.CREATED, Status.PRICE_CALCULATED):
        request.status = Status.PRICE_CALCULATED if tariff else Status.CREATED


def _take_from_other_requests(request, parcels):
    """Посылка в одной живой заявке. Перешла сюда — из старой её убираем.

    Старая заявка, оставшаяся без посылок, отменяется молча: клиент сам
    перенёс посылку, уведомлять его о «доставка отменена» незачем.
    """
    ids = [p.id for p in parcels]
    others = (
        _live_requests_of(request.user_id)
        .exclude(pk=request.pk)
        .filter(status__in=EDITABLE_STATUSES)
    )
    if not ids:
        return
    for other in others.filter(Q(parcels__id__in=ids) | Q(parcel_id__in=ids)).distinct():
        other.parcels.remove(*parcels)
        rest = list(other.parcels.all())
        if rest or other.is_standing:
            _apply_parcels(other, rest)
            other.save()
        else:
            other.parcel = None
            other.status = Status.CANCELLED
            other._silent = True
            other.save()


def save_client_request(user, data, instance=None, partial=False):
    """Создать или обновить заявку клиента. Возвращает (заявка, создана ли).

    ``parcels`` — весь состав целиком; старое ``parcel`` — добавить одну
    посылку к тому, что уже есть (так шлют установленные версии, по заявке на
    посылку). Без посылок заявка постоянная: забирает всё, что уже лежит в
    ПВЗ, и подхватывает то, что придёт.
    """
    created = instance is None
    if created:
        instance = CityDeliveryRequest(user=user)
    elif instance.status not in EDITABLE_STATUSES:
        raise DeliveryInProgress(instance)

    for field in _CLIENT_FIELDS:
        if field in data:
            value = data[field]
            setattr(instance, field, "" if value is None and field in _TEXT_FIELDS else value)
        elif not partial:
            setattr(instance, field, "" if field in _TEXT_FIELDS else None)
    # Точка и предложение — одно «куда»: выбрал одно — другое снимается.
    if partial:
        if data.get("delivery_point") and "suggested_point" not in data:
            instance.suggested_point = ""
        if data.get("suggested_point") and "delivery_point" not in data:
            instance.delivery_point = None

    current = list(instance.parcels.all()) if instance.pk else []
    if "parcels" in data:
        parcels = list(data["parcels"])
    elif data.get("parcel"):
        parcels = current + [p for p in [data["parcel"]] if p not in current]
    else:
        parcels = current

    if "is_standing" in data:
        instance.is_standing = data["is_standing"]
    elif "parcels" in data or data.get("parcel"):
        instance.is_standing = not parcels
    elif not partial:
        # Повторный POST без посылок — «всё моё везите сюда».
        instance.is_standing = True

    if instance.is_standing:
        parcels += [
            p for p in waiting_parcels(user.id, exclude_request_id=instance.pk)
            if p not in parcels
        ]

    with transaction.atomic():
        _apply_parcels(instance, parcels)
        instance.save()
        _take_from_other_requests(instance, parcels)
        instance.parcels.set(parcels)
    return instance, created


def cancel_client_request(instance):
    if instance.status not in EDITABLE_STATUSES:
        raise DeliveryInProgress(instance)
    instance.status = Status.CANCELLED
    instance._silent = True
    instance.save()
    return instance


def attach_to_standing_request(parcel):
    """Посылка пришла в ПВЗ (или нашла хозяина уже в ПВЗ) — в постоянную заявку.

    Только в заявку, которую курьер ещё не взял: в уехавшую не подкинешь.
    """
    from parcels.models import Parcel

    if parcel.user_id is None or parcel.status != Parcel.Status.AT_PICKUP_POINT:
        return None
    request = (
        CityDeliveryRequest.objects.filter(
            user_id=parcel.user_id, is_standing=True, status__in=EDITABLE_STATUSES
        )
        .order_by("-created_at")
        .first()
    )
    if request is None:
        return None
    if parcel.city_deliveries.exclude(status__in=CLOSED_STATUSES).exists():
        return None
    request.parcels.add(parcel)
    _apply_parcels(request, list(request.parcels.all()))
    request._silent = True
    request.save()
    return request


def request_parcels(request):
    """Все посылки заявки: состав плюс старое поле (заявки до переработки)."""
    parcels = {p.id: p for p in request.parcels.all()}
    if request.parcel_id and request.parcel_id not in parcels:
        parcels[request.parcel_id] = request.parcel
    return list(parcels.values())


def on_status_changed(request, old_status):
    """Панель сменила статус: посылки едут вместе с заявкой."""
    from parcels.models import Parcel
    from parcels.services import update_parcel_status

    if request.status == old_status:
        return
    if request.status == Status.IN_DELIVERY:
        for parcel in request_parcels(request):
            if parcel.status != Parcel.Status.CITY_DELIVERY:
                update_parcel_status(
                    parcel, Parcel.Status.CITY_DELIVERY, comment="Передан на доставку"
                )
    elif request.status == Status.DELIVERED:
        if request.delivered_at is None:
            request.delivered_at = timezone.now()
            request.save(update_fields=["delivered_at"])
        for parcel in request_parcels(request):
            if parcel.status != Parcel.Status.DELIVERED:
                update_parcel_status(
                    parcel, Parcel.Status.DELIVERED, comment="Доставлено по городу"
                )
        if request.is_standing:
            reopen_standing(request)


def reopen_standing(done):
    """Постоянная заявка после доставки открывается заново с той же точкой.

    Клиент сказал «куда» один раз — следующая партия поедет туда же. Новая
    заявка, а не та же: доставленная остаётся в истории как есть.
    """
    fresh = CityDeliveryRequest(
        user=done.user,
        is_standing=True,
        delivery_point=done.delivery_point,
        suggested_point=done.suggested_point,
        address=done.address,
        recipient_name=done.recipient_name,
        recipient_phone=done.recipient_phone,
        comment=done.comment,
        delivery_time_slot=done.delivery_time_slot,
    )
    parcels = waiting_parcels(done.user_id)
    _apply_parcels(fresh, parcels)
    fresh._silent = True
    fresh.save()
    fresh.parcels.set(parcels)
    return fresh


def normalize_suggestion(text: str) -> str:
    """Ключ группировки предложений: без регистра, лишних пробелов и «ё».

    «Ошский рынок» и «  ошский   РЫНОК » — одно и то же место. «Ош базар» так
    не склеить — для этого оператор переводит заявки в точку по тексту.
    """
    value = (text or "").lower().replace("ё", "е")
    value = re.sub(r"\s+", " ", value).strip()
    return value.strip(" .,;:-")


def open_suggestions(cargo_id=None, pickup_id=None):
    """Живые заявки с предложенной точкой, которую ещё не перевели в справочник."""
    qs = (
        CityDeliveryRequest.objects.exclude(status__in=CLOSED_STATUSES)
        .filter(delivery_point__isnull=True)
        .exclude(suggested_point="")
    )
    if cargo_id:
        qs = qs.filter(user__cargo_id=cargo_id)
    if pickup_id:
        qs = qs.filter(user__pickup_point_id=pickup_id)
    return qs


def suggested_points_count(cargo_id, pickup_id=None):
    return open_suggestions(cargo_id, pickup_id).count()


def group_suggestions(queryset):
    """Предложения, сгруппированные по месту, самые востребованные сверху.

    Подпись группы — самое частое написание как есть, а не нормализованный
    ключ: оператор видит то, что писали клиенты.
    """
    groups = {}
    for req in queryset.order_by("created_at").values(
        "id", "user_id", "suggested_point", "created_at"
    ):
        key = normalize_suggestion(req["suggested_point"])
        if not key:
            continue
        g = groups.setdefault(
            key,
            {"spellings": Counter(), "users": set(), "ids": [], "first": None, "last": None},
        )
        g["spellings"][req["suggested_point"].strip()] += 1
        g["users"].add(req["user_id"])
        g["ids"].append(req["id"])
        g["first"] = g["first"] or req["created_at"]
        g["last"] = req["created_at"]
    rows = [
        {
            "text": g["spellings"].most_common(1)[0][0],
            "clients_count": len(g["users"]),
            "requests_count": len(g["ids"]),
            "request_ids": g["ids"],
            "first_seen": g["first"],
            "last_seen": g["last"],
        }
        for g in groups.values()
    ]
    rows.sort(key=lambda r: (-r["clients_count"], -r["requests_count"], r["text"]))
    return rows


def adopt_suggestions(point, text, cargo_id=None):
    """Перевести в точку все живые заявки с таким же предложением."""
    key = normalize_suggestion(text)
    if not key:
        return 0
    ids = [
        row["id"]
        for row in open_suggestions(cargo_id).values("id", "suggested_point")
        if normalize_suggestion(row["suggested_point"]) == key
    ]
    return CityDeliveryRequest.objects.filter(pk__in=ids).update(
        delivery_point=point, suggested_point="", updated_at=timezone.now()
    )
