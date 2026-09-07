"""Пагинация истории операций.

Раньше стояла обрезка qs[:500]: операции старше пятисотой были недостижимы
вообще, а ответ рос вместе с историей — страницу открывают с телефона на
складе.
"""

import pytest

from parcels.models import Parcel, ParcelStatusHistory
from tests.factories import CargoCompanyFactory, UserFactory


@pytest.fixture
def history(db, cargo_admin):
    cargo = cargo_admin.cargo
    client = UserFactory(cargo=cargo)
    parcel = Parcel.objects.create(
        cargo=cargo, user=client, client_code=client.client_code,
        track_number="T-HIST", status="at_pickup_point",
    )
    for _ in range(120):
        ParcelStatusHistory.objects.create(
            parcel=parcel, status=Parcel.Status.AT_PICKUP_POINT, changed_by=cargo_admin
        )
    return parcel


@pytest.mark.django_db
def test_first_page_is_limited(cargo_admin_client, history):
    # Создание посылки само пишет запись в историю — считаем от факта.
    expected = ParcelStatusHistory.objects.filter(
        status=Parcel.Status.AT_PICKUP_POINT
    ).count()

    r = cargo_admin_client.get("/api/history/?type=receive")
    assert r.status_code == 200
    assert r.data["count"] == expected
    # По умолчанию отдаём страницу, а не всю историю.
    assert len(r.data["results"]) == 50


@pytest.mark.django_db
def test_offset_reaches_older_records(cargo_admin_client, history):
    first = cargo_admin_client.get("/api/history/?type=receive&limit=50").data["results"]
    second = cargo_admin_client.get("/api/history/?type=receive&limit=50&offset=50").data["results"]

    assert len(second) == 50
    # Страницы не пересекаются — иначе догрузка дублировала бы строки.
    assert {r["id"] for r in first}.isdisjoint({r["id"] for r in second})


@pytest.mark.django_db
def test_can_reach_beyond_old_500_cap(cargo_admin_client, cargo_admin):
    """Ровно то, что было невозможно: операции за пределами пятисотой."""
    cargo = cargo_admin.cargo
    client = UserFactory(cargo=cargo)
    parcel = Parcel.objects.create(
        cargo=cargo, user=client, client_code=client.client_code,
        track_number="T-DEEP", status="at_pickup_point",
    )
    ParcelStatusHistory.objects.bulk_create(
        ParcelStatusHistory(parcel=parcel, status=Parcel.Status.AT_PICKUP_POINT, changed_by=cargo_admin)
        for _ in range(520)
    )

    total = ParcelStatusHistory.objects.filter(
        status=Parcel.Status.AT_PICKUP_POINT
    ).count()
    assert total > 500

    r = cargo_admin_client.get(f"/api/history/?type=receive&limit=10&offset={total - 5}")
    assert r.status_code == 200
    assert r.data["count"] == total
    assert len(r.data["results"]) == 5


@pytest.mark.django_db
def test_limit_is_capped(cargo_admin_client, history):
    """Клиент не должен уметь запросить всю историю одним запросом."""
    r = cargo_admin_client.get("/api/history/?type=receive&limit=100000")
    assert len(r.data["results"]) <= 200


@pytest.mark.django_db
def test_filters_still_apply_with_pagination(cargo_admin_client, history):
    r = cargo_admin_client.get("/api/history/?type=issue")
    assert r.data["count"] == 0
