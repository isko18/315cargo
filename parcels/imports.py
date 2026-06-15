"""CSV import for parcels.

Supports a simple CSV with columns:
  track_number,client_code,status,location,weight,volume,delivery_price

Lookup of the user is done via ``client_code``. Existing parcels are updated.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import TextIOWrapper
from typing import IO

from django.contrib.auth import get_user_model
from django.db import transaction

from .models import Parcel

User = get_user_model()


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


def _decimal(value: str | None):
    if value is None or value == "":
        return None
    try:
        return Decimal(value.replace(",", "."))
    except (InvalidOperation, AttributeError):
        return None


def _ensure_text_stream(file_obj: IO, encoding: str):
    # Detect binary streams: TextIOWrapper, StringIO behave like text.
    # InMemoryUploadedFile / BytesIO / open(..., 'rb') return bytes from read().
    if hasattr(file_obj, "read"):
        try:
            sample = file_obj.read(0)
            if isinstance(sample, bytes):
                return TextIOWrapper(file_obj, encoding=encoding, newline="")
        except Exception:
            pass
    return file_obj


@transaction.atomic
def import_parcels_from_csv(file_obj: IO, encoding: str = "utf-8", cargo=None) -> ImportResult:
    """Import parcels from a CSV stream.

    ``cargo`` scopes the ``client_code`` lookup to a single cargo company so an
    import cannot attach parcels to a client in another cargo (``client_code``
    is unique only per cargo). Pass ``None`` only for a global superuser import.
    """
    stream = _ensure_text_stream(file_obj, encoding)
    reader = csv.DictReader(stream)
    result = ImportResult()
    valid_statuses = set(Parcel.Status.values)

    for row_index, row in enumerate(reader, start=2):
        track_number = (row.get("track_number") or "").strip()
        client_code = (row.get("client_code") or "").strip()
        if not track_number or not client_code:
            result.errors.append(
                f"Строка {row_index}: track_number и client_code обязательны"
            )
            result.skipped += 1
            continue

        user_qs = User.objects.filter(client_code=client_code)
        if cargo is not None:
            user_qs = user_qs.filter(cargo=cargo)
        matches = list(user_qs[:2])
        if len(matches) > 1:
            # Without a cargo scope the same client_code can exist in several
            # cargos — refuse rather than guess the owner.
            result.errors.append(
                f"Строка {row_index}: код {client_code} найден в нескольких карго, "
                f"импорт неоднозначен"
            )
            result.skipped += 1
            continue
        user = matches[0] if matches else None
        if not user:
            result.errors.append(
                f"Строка {row_index}: клиент с кодом {client_code} не найден"
            )
            result.skipped += 1
            continue

        # Guard against reassigning an existing parcel to a different owner:
        # update_or_create matches on track_number alone, so a row resolving to
        # another client would otherwise silently steal the parcel.
        existing = Parcel.objects.filter(track_number=track_number).first()
        if existing and existing.user_id != user.id:
            result.errors.append(
                f"Строка {row_index}: трек {track_number} уже принадлежит другому клиенту"
            )
            result.skipped += 1
            continue

        status = (row.get("status") or Parcel.Status.CREATED).strip()
        if status not in valid_statuses:
            result.errors.append(
                f"Строка {row_index}: неизвестный статус '{status}'"
            )
            result.skipped += 1
            continue

        defaults = {
            "cargo_id": user.cargo_id,
            "user": user,
            "client_code": client_code,
            "status": status,
            "location": (row.get("location") or "").strip(),
            "weight": _decimal(row.get("weight")),
            "volume": _decimal(row.get("volume")),
            "delivery_price": _decimal(row.get("delivery_price")),
        }

        parcel, created = Parcel.objects.update_or_create(
            track_number=track_number,
            defaults=defaults,
        )
        if created:
            result.created += 1
        else:
            result.updated += 1

    return result
