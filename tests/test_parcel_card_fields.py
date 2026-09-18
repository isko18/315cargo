"""Поля карточки товара: расчёт, оплата, габариты, уведомление.

Здесь важны две вещи, которые легко сломать незаметно: объём должен
считаться из габаритов сам (иначе оператор вводит одно и то же дважды и
цифры разъезжаются), а отметка об уведомлении — ставиться только тогда,
когда уведомление действительно ушло.
"""

import pytest

from parcels.models import Parcel
from tests.factories import UserFactory


@pytest.fixture
def parcel(db, cargo_admin):
    cargo = cargo_admin.cargo
    client = UserFactory(cargo=cargo)
    return Parcel.objects.create(
        cargo=cargo,
        user=client,
        client_code=client.client_code,
        track_number="CARD-1",
        status="created",
    )


@pytest.mark.django_db
def test_patch_writes_card_fields(cargo_admin_client, parcel):
    r = cargo_admin_client.patch(
        f"/api/manage/parcels/{parcel.id}/",
        {
            "payment_status": "paid",
            "receipt_method": "city_delivery",
            "delivery_address": "Ош, Курманжан Датка 12",
            "usd_rate": "87.5000",
            "client_price": "1250.00",
            "crating": True,
            "packaging": True,
        },
        format="json",
    )

    assert r.status_code == 200
    parcel.refresh_from_db()
    assert parcel.payment_status == "paid"
    assert parcel.receipt_method == "city_delivery"
    assert parcel.delivery_address == "Ош, Курманжан Датка 12"
    assert str(parcel.client_price) == "1250.00"
    assert parcel.crating and parcel.packaging


@pytest.mark.django_db
def test_volume_is_computed_from_dimensions(cargo_admin_client, parcel):
    """Оператор меряет коробку, а не м³."""
    r = cargo_admin_client.patch(
        f"/api/manage/parcels/{parcel.id}/",
        {"length_cm": "50", "width_cm": "40", "height_cm": "30"},
        format="json",
    )

    assert r.status_code == 200
    parcel.refresh_from_db()
    # 50 × 40 × 30 см = 0.06 м³
    assert str(parcel.volume) == "0.060"


@pytest.mark.django_db
def test_volume_untouched_while_dimensions_incomplete(cargo_admin_client, parcel):
    """По двум сторонам объём не считается — лучше пусто, чем неправда."""
    cargo_admin_client.patch(
        f"/api/manage/parcels/{parcel.id}/",
        {"length_cm": "50", "width_cm": "40"},
        format="json",
    )

    parcel.refresh_from_db()
    assert parcel.volume is None


@pytest.mark.django_db
def test_payment_status_defaults_to_unpaid(parcel):
    assert parcel.payment_status == Parcel.PaymentStatus.UNPAID
    assert parcel.receipt_method == Parcel.ReceiptMethod.PICKUP


@pytest.mark.django_db
def test_notified_at_moves_with_each_notification(cargo_admin_client, parcel):
    """Отметка показывает последнее уведомление, а не первое."""
    parcel.refresh_from_db()
    before = parcel.notified_at  # посылку уже завели — клиент получил статус
    assert before is not None

    cargo_admin_client.patch(
        f"/api/manage/parcels/{parcel.id}/", {"status": "at_pickup_point"}, format="json"
    )

    parcel.refresh_from_db()
    assert parcel.notified_at > before


@pytest.mark.django_db
def test_notified_at_stays_empty_for_unassigned_parcel(cargo_admin, cargo_admin_client):
    """Посылке без клиента уведомлять некого — отметки быть не должно."""
    orphan = Parcel.objects.create(
        cargo=cargo_admin.cargo, user=None, client_code="", track_number="CARD-2",
        status="created",
    )

    cargo_admin_client.patch(
        f"/api/manage/parcels/{orphan.id}/", {"status": "arrived_kyrgyzstan"}, format="json"
    )

    orphan.refresh_from_db()
    assert orphan.status == "arrived_kyrgyzstan"
    assert orphan.notified_at is None


@pytest.mark.django_db
def test_card_fields_are_readable_in_list(cargo_admin_client, parcel):
    parcel.payment_status = "paid"
    parcel.save(update_fields=["payment_status"])

    rows = cargo_admin_client.get("/api/parcels/?limit=500").data["results"]
    row = next(r for r in rows if r["id"] == parcel.id)
    assert row["payment_status"] == "paid"
    assert row["payment_status_display_name"] == "Оплачен"
    assert row["receipt_method"] == "pickup"
    assert "usd_rate" in row and "client_price" in row


@pytest.mark.django_db
def test_notified_at_is_not_writable(cargo_admin_client, parcel):
    """Отметка об уведомлении — факт, а не поле ввода."""
    parcel.refresh_from_db()
    before = parcel.notified_at

    cargo_admin_client.patch(
        f"/api/manage/parcels/{parcel.id}/",
        {"notified_at": "2020-01-01T00:00:00Z", "location": "A1"},
        format="json",
    )

    parcel.refresh_from_db()
    assert parcel.notified_at == before
    assert parcel.location == "A1"
