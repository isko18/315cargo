"""Правка посылок сотрудником: PATCH и пачки.

Главный риск тут не функциональность, а границы: посылка чужого карго или
чужого ПВЗ не должна правиться, а оператор Китая — ставить статусы Кыргызстана.
"""

import pytest

from parcels.models import Parcel, ParcelStatusHistory
from tests.factories import CargoCompanyFactory, PickupPointFactory, UserFactory


@pytest.fixture
def china_operator(db):
    """Оператор склада в Китае: без карго, работает по всем сразу."""
    from users.models import User

    return User.objects.create(
        phone="+996700000777", is_staff=True, is_china_staff=True, cargo=None
    )


@pytest.fixture
def parcel(db, cargo_admin):
    cargo = cargo_admin.cargo
    # Без тарифа цена не считается — а мы её проверяем.
    cargo.price_per_kg_kgs = 100
    cargo.save(update_fields=["price_per_kg_kgs"])
    client = UserFactory(cargo=cargo)
    return Parcel.objects.create(
        cargo=cargo,
        user=client,
        client_code=client.client_code,
        track_number="MP-1",
        status="created",
    )


@pytest.mark.django_db
def test_patch_updates_fields(cargo_admin_client, parcel):
    point = PickupPointFactory(cargo=parcel.cargo)
    r = cargo_admin_client.patch(
        f"/api/manage/parcels/{parcel.id}/",
        {"weight": "1.500", "location": "Стеллаж 12", "pickup_point": point.id},
        format="json",
    )
    assert r.status_code == 200
    parcel.refresh_from_db()
    assert str(parcel.weight) == "1.500"
    assert parcel.pickup_point_id == point.id
    # Цена пересчитывается по тарифу карго, а не берётся с клиента.
    assert parcel.delivery_price is not None


@pytest.mark.django_db
def test_patch_status_writes_history_once(cargo_admin_client, parcel):
    """Смена статуса раньше шла через scan/ и писала лишнюю строку приёмки."""
    before = ParcelStatusHistory.objects.filter(parcel=parcel).count()

    r = cargo_admin_client.patch(
        f"/api/manage/parcels/{parcel.id}/", {"status": "at_pickup_point"}, format="json"
    )

    assert r.status_code == 200
    parcel.refresh_from_db()
    assert parcel.status == "at_pickup_point"
    assert ParcelStatusHistory.objects.filter(parcel=parcel).count() == before + 1


@pytest.mark.django_db
def test_patch_rejects_pickup_from_other_cargo(cargo_admin_client, parcel):
    """Чужой ПВЗ сделал бы посылку невидимой для обеих сторон."""
    foreign = PickupPointFactory(cargo=CargoCompanyFactory())

    r = cargo_admin_client.patch(
        f"/api/manage/parcels/{parcel.id}/", {"pickup_point": foreign.id}, format="json"
    )

    assert r.status_code == 400
    parcel.refresh_from_db()
    assert parcel.pickup_point_id is None


@pytest.mark.django_db
def test_patch_rejects_unknown_client_code(cargo_admin_client, parcel):
    r = cargo_admin_client.patch(
        f"/api/manage/parcels/{parcel.id}/", {"client_code": "NOPE-1"}, format="json"
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_parcel_of_other_cargo_is_not_found(cargo_admin_client):
    """Чужая посылка отдаётся как 404, а не 403: существование не раскрываем."""
    other = CargoCompanyFactory()
    foreign = Parcel.objects.create(
        cargo=other, user=None, client_code="", track_number="MP-FOREIGN", status="created"
    )

    r = cargo_admin_client.patch(
        f"/api/manage/parcels/{foreign.id}/", {"status": "issued"}, format="json"
    )

    assert r.status_code == 404
    foreign.refresh_from_db()
    assert foreign.status == "created"


@pytest.mark.django_db
def test_china_operator_cannot_set_kyrgyz_status(api_client, china_operator, parcel):
    from rest_framework_simplejwt.tokens import RefreshToken

    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(china_operator).access_token}"
    )
    r = api_client.patch(
        f"/api/manage/parcels/{parcel.id}/", {"status": "at_pickup_point"}, format="json"
    )
    assert r.status_code == 403


# --- Пачки ---


@pytest.mark.django_db
def test_bulk_scan_reports_each_row(cargo_admin_client, cargo_admin):
    """Оператору нужно знать, какие треки не прошли, а не только счётчик."""
    client = UserFactory(cargo=cargo_admin.cargo)

    r = cargo_admin_client.post(
        "/api/manage/parcels/bulk-scan/",
        {
            "status": "at_pickup_point",
            "items": [
                {"track_number": "BULK-1", "weight": "0.5"},
                {"track_number": "BULK-2", "client_code": client.client_code},
                {"track_number": "", "weight": "1"},
            ],
        },
        format="json",
    )

    assert r.status_code == 200
    assert r.data["created"] + r.data["updated"] == 2
    assert len(r.data["errors"]) == 1
    assert r.data["errors"][0]["index"] == 2


@pytest.mark.django_db
def test_bad_row_does_not_cancel_the_batch(cargo_admin_client, cargo_admin):
    """Одна плохая строка не должна отменять всю накладную."""
    r = cargo_admin_client.post(
        "/api/manage/parcels/bulk-scan/",
        {
            "status": "at_pickup_point",
            "items": [
                {"track_number": "OK-1"},
                {"track_number": "BAD-1", "client_code": "НЕТ-ТАКОГО"},
                {"track_number": "OK-2"},
            ],
        },
        format="json",
    )

    assert r.status_code == 200
    assert Parcel.objects.filter(track_number__in=["OK-1", "OK-2"]).count() == 2


@pytest.mark.django_db
def test_bulk_status_changes_selected(cargo_admin_client, cargo_admin):
    cargo = cargo_admin.cargo
    client = UserFactory(cargo=cargo)
    ids = [
        Parcel.objects.create(
            cargo=cargo, user=client, client_code=client.client_code,
            track_number=f"BS-{i}", status="at_pickup_point",
        ).id
        for i in range(3)
    ]

    r = cargo_admin_client.post(
        "/api/manage/parcels/bulk-status/", {"ids": ids, "status": "issued"}, format="json"
    )

    assert r.status_code == 200
    assert r.data["updated"] == 3
    assert Parcel.objects.filter(id__in=ids, status="issued").count() == 3


@pytest.mark.django_db
def test_bulk_status_skips_foreign_parcels(cargo_admin_client, cargo_admin):
    """Чужая посылка попадает в errors, а не молча меняется."""
    cargo = cargo_admin.cargo
    mine = Parcel.objects.create(
        cargo=cargo, user=None, client_code="", track_number="BS-MINE", status="at_pickup_point"
    )
    foreign = Parcel.objects.create(
        cargo=CargoCompanyFactory(), user=None, client_code="",
        track_number="BS-FOREIGN", status="at_pickup_point",
    )

    r = cargo_admin_client.post(
        "/api/manage/parcels/bulk-status/",
        {"ids": [mine.id, foreign.id], "status": "issued"},
        format="json",
    )

    assert r.data["updated"] == 1
    assert [e["id"] for e in r.data["errors"]] == [foreign.id]
    foreign.refresh_from_db()
    assert foreign.status == "at_pickup_point"
