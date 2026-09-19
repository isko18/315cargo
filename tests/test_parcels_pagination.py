"""Постраничный список посылок и поиск по клиенту.

Эндпоинт отдавал весь список одним куском: на нашем карго это 1 МБ, у крупного
— десятки мегабайт и таймаут на телефоне.

Пагинация включается только по ?limit=. Без параметра ответ обязан остаться
голым массивом: форму {count, next, previous, results} не разобрать уже
установленным приложениям, а обновить их одновременно с бэкендом нельзя.
"""

import pytest

from parcels.models import Parcel
from tests.factories import CargoCompanyFactory, UserFactory


@pytest.fixture
def many_parcels(db, cargo_admin):
    cargo = cargo_admin.cargo
    client = UserFactory(cargo=cargo, full_name="Иванов Иван", phone="+996700123456")
    Parcel.objects.bulk_create(
        Parcel(
            cargo=cargo, user=client, client_code=client.client_code,
            track_number=f"P-{i:04d}", status="created",
        )
        for i in range(120)
    )
    return client


@pytest.mark.django_db
def test_list_without_limit_stays_a_plain_array(cargo_admin_client, many_parcels):
    """Клиент, не просивший страницу, должен получить прежний формат."""
    r = cargo_admin_client.get("/api/parcels/")

    assert r.status_code == 200
    assert isinstance(r.data, list)
    assert len(r.data) == 120


@pytest.mark.django_db
def test_list_is_paginated_when_limit_asked(cargo_admin_client, many_parcels):
    r = cargo_admin_client.get("/api/parcels/?limit=50")
    assert r.status_code == 200
    assert r.data["count"] == 120
    assert len(r.data["results"]) == 50


@pytest.mark.django_db
def test_offset_reaches_rest(cargo_admin_client, many_parcels):
    first = cargo_admin_client.get("/api/parcels/?limit=50").data["results"]
    second = cargo_admin_client.get("/api/parcels/?limit=50&offset=50").data["results"]
    assert len(second) == 50
    # Страницы не пересекаются — иначе подгрузка по прокрутке дублировала бы.
    assert {p["id"] for p in first}.isdisjoint({p["id"] for p in second})


@pytest.mark.django_db
def test_limit_capped_but_fits_one_client(cargo_admin_client, many_parcels):
    """Выдаче нужны все посылки клиента одним списком, поэтому потолок высокий."""
    r = cargo_admin_client.get("/api/parcels/?limit=100000")
    assert len(r.data["results"]) == 120


@pytest.mark.django_db
def test_search_finds_by_client_name_and_phone(cargo_admin_client, many_parcels):
    """На выдаче ищут по фамилии и телефону, а не только по треку."""
    by_name = cargo_admin_client.get("/api/parcels/?search=Иванов&limit=50")
    by_phone = cargo_admin_client.get("/api/parcels/?search=700123456&limit=50")
    assert by_name.data["count"] == 120
    assert by_phone.data["count"] == 120


@pytest.mark.django_db
def test_status_in_accepts_comma_separated(cargo_admin_client, cargo_admin):
    """Формат, который уже шлёт мобильная панель."""
    cargo = cargo_admin.cargo
    client = UserFactory(cargo=cargo)
    for i, st in enumerate(("at_pickup_point", "in_transit", "created")):
        Parcel.objects.create(
            cargo=cargo, user=client, client_code=client.client_code,
            track_number=f"S-{i}", status=st,
        )

    r = cargo_admin_client.get("/api/parcels/?status_in=at_pickup_point,in_transit")
    assert {p["status"] for p in r.data} == {"at_pickup_point", "in_transit"}


@pytest.mark.django_db
def test_parcel_exposes_pickup_point_id(cargo_admin_client, cargo_admin, pickup_point):
    """По названию ПВЗ сопоставлять нельзя — они не уникальны и меняются."""
    cargo = cargo_admin.cargo
    client = UserFactory(cargo=cargo, pickup_point=pickup_point)
    Parcel.objects.create(
        cargo=cargo, user=client, client_code=client.client_code,
        track_number="PP-1", status="created",
    )

    row = cargo_admin_client.get("/api/parcels/?search=PP-1").data[0]
    assert row["pickup_point"] == pickup_point.id
    assert row["pickup_point_title"] == pickup_point.title
