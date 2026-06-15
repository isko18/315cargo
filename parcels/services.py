import logging

from django.db import transaction

from .models import Parcel

logger = logging.getLogger(__name__)


class ScanError(Exception):
    """Доменная ошибка сканирования (мапится на 4xx во view)."""

    def __init__(self, message, code="invalid"):
        super().__init__(message)
        self.message = message
        self.code = code


@transaction.atomic
def scan_parcel(track_number, cargo, actor=None, status=None, request=None):
    """Зарегистрировать посылку по трек-номеру (сканер, одно поле).

    Возвращает кортеж ``(result, parcel)`` где ``result`` — одно из
    ``updated`` / ``created_from_order`` / ``created_pending``.
    """
    from orders.models import Order

    from common.audit import log_audit
    from common.models import AuditLog

    track_number = (track_number or "").strip()
    if not track_number:
        raise ScanError("track_number обязателен", code="invalid")
    if cargo is None:
        raise ScanError("Не определён карго-центр", code="no_cargo")

    target_status = status or Parcel.Status.ARRIVED_CHINA_WAREHOUSE
    if target_status not in Parcel.Status.values:
        raise ScanError("Неизвестный статус", code="invalid")

    existing = Parcel.objects.select_related("user").filter(track_number=track_number).first()
    if existing is not None:
        if existing.cargo_id != cargo.id:
            raise ScanError(
                "Трек уже зарегистрирован в другом карго-центре", code="conflict"
            )
        update_parcel_status(existing, target_status, changed_by=actor)
        result, parcel = "updated", existing
    else:
        order = (
            Order.objects.select_related("user")
            .filter(track_number=track_number, user__cargo_id=cargo.id)
            .first()
        )
        if order is not None:
            parcel = Parcel(
                cargo=cargo,
                user=order.user,
                order=order,
                track_number=track_number,
                client_code=order.user.client_code or "",
                status=target_status,
            )
            parcel.apply_status_timestamps()
            parcel._status_changed_by = actor
            parcel.save()
            result = "created_from_order"
        else:
            parcel = Parcel(
                cargo=cargo,
                user=None,
                track_number=track_number,
                client_code="",
                status=target_status,
            )
            parcel.apply_status_timestamps()
            parcel._status_changed_by = actor
            parcel.save()
            result = "created_pending"

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
    extra_fields = parcel.apply_status_timestamps()
    parcel.save(update_fields=["status", "updated_at", *extra_fields])
    logger.info(
        "Parcel status updated",
        extra={"parcel_id": parcel.id, "track_number": parcel.track_number, "status": status},
    )
    return parcel
