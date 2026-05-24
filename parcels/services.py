import logging

from .models import Parcel

logger = logging.getLogger(__name__)


def update_parcel_status(parcel, status, comment=None, changed_by=None):
    if status not in Parcel.Status.values:
        raise ValueError("Invalid parcel status")
    parcel._status_comment = comment or ""
    parcel._status_changed_by = changed_by
    parcel.status = status
    parcel.save(update_fields=("status", "updated_at"))
    logger.info(
        "Parcel status updated",
        extra={"parcel_id": parcel.id, "track_number": parcel.track_number, "status": status},
    )
    return parcel
