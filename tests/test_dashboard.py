from datetime import timedelta

import pytest
from django.utils import timezone

from parcels.models import Parcel
from tests.factories import ParcelFactory, PickupPointFactory, UserFactory


@pytest.mark.django_db
def test_dashboard_pickup_bound_operator_forced_scope(api_client):
    from rest_framework_simplejwt.tokens import RefreshToken

    from tests.factories import CargoCompanyFactory

    cargo = CargoCompanyFactory()
    pp1 = PickupPointFactory(cargo=cargo, title="ПВЗ 1")
    pp2 = PickupPointFactory(cargo=cargo, title="ПВЗ 2")
    client1 = UserFactory(cargo=cargo, pickup_point=pp1)
    client2 = UserFactory(cargo=cargo, pickup_point=pp2)
    now = timezone.now()
    for cl in (client1, client2):
        p = ParcelFactory(user=cl, cargo=cargo, status=Parcel.Status.ISSUED)
        Parcel.objects.filter(pk=p.pk).update(issued_at=now, delivery_price="5.00")

    operator = UserFactory(cargo=cargo, is_staff=True, pickup_point=pp1, allowed_tabs=["analytics"])
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(operator).access_token}"
    )
    # Пытаемся подменить ПВЗ на pp2 — должно игнорироваться.
    r = api_client.get(f"/api/manage/dashboard/?period=all&pickup_point={pp2.id}")
    assert r.status_code == 200
    assert r.data["pickup"]["id"] == pp1.id
    assert r.data["period_issued_count"] == 1  # только клиент pp1
    assert r.data["users_count"] == 1


@pytest.mark.django_db
def test_dashboard_period_filter_scopes_kpis(cargo_admin_client):
    cargo = cargo_admin_client.user.cargo
    client = UserFactory(cargo=cargo)
    now = timezone.now()

    p_recent = ParcelFactory(user=client, cargo=cargo, status=Parcel.Status.ISSUED)
    Parcel.objects.filter(pk=p_recent.pk).update(
        issued_at=now, delivery_price="10.00", weight="2.000"
    )
    p_old = ParcelFactory(user=client, cargo=cargo, status=Parcel.Status.ISSUED)
    Parcel.objects.filter(pk=p_old.pk).update(
        issued_at=now - timedelta(days=60), delivery_price="5.00", weight="1.000"
    )

    # За 7 дней виден только свежий.
    r = cargo_admin_client.get("/api/manage/dashboard/?period=7d")
    assert r.status_code == 200
    assert r.data["period"]["key"] == "7d"
    assert r.data["period_issued_count"] == 1
    assert r.data["period_revenue_usd"] == 10.0
    assert r.data["period_avg_check_usd"] == 10.0
    assert isinstance(r.data["timeseries"], list) and len(r.data["timeseries"]) == 7

    # За всё время — обе выдачи.
    r_all = cargo_admin_client.get("/api/manage/dashboard/?period=all")
    assert r_all.data["period_issued_count"] == 2
    assert r_all.data["period_revenue_usd"] == 15.0
    assert r_all.data["top_clients"][0]["client_code"] == client.client_code
    assert r_all.data["top_clients"][0]["revenue"] == 15.0


@pytest.mark.django_db
def test_dashboard_scopes_by_pickup_point(cargo_admin_client):
    from tests.factories import PickupPointFactory

    cargo = cargo_admin_client.user.cargo
    pp_a = PickupPointFactory(cargo=cargo, title="ПВЗ A")
    pp_b = PickupPointFactory(cargo=cargo, title="ПВЗ B")
    client_a = UserFactory(cargo=cargo, pickup_point=pp_a)
    client_b = UserFactory(cargo=cargo, pickup_point=pp_b)
    now = timezone.now()

    for client in (client_a, client_b):
        p = ParcelFactory(user=client, cargo=cargo, status=Parcel.Status.ISSUED)
        Parcel.objects.filter(pk=p.pk).update(issued_at=now, delivery_price="9.00")

    # Без ПВЗ — обе выдачи.
    r_all = cargo_admin_client.get("/api/manage/dashboard/?period=all")
    assert r_all.data["pickup"]["id"] is None
    assert r_all.data["period_issued_count"] == 2

    # Скоуп по ПВЗ A — только выдача клиента A.
    r_a = cargo_admin_client.get(f"/api/manage/dashboard/?period=all&pickup_point={pp_a.id}")
    assert r_a.data["pickup"]["id"] == pp_a.id
    assert r_a.data["pickup"]["title"] == "ПВЗ A"
    assert r_a.data["period_issued_count"] == 1
    assert r_a.data["period_revenue_usd"] == 9.0
    assert r_a.data["users_count"] == 1
    assert r_a.data["parcels_count"] == 1


@pytest.mark.django_db
def test_dashboard_custom_date_range(cargo_admin_client):
    cargo = cargo_admin_client.user.cargo
    client = UserFactory(cargo=cargo)
    issued = timezone.now() - timedelta(days=10)
    p = ParcelFactory(user=client, cargo=cargo, status=Parcel.Status.ISSUED)
    Parcel.objects.filter(pk=p.pk).update(issued_at=issued, delivery_price="7.00")

    # Дата берётся в активной таймзоне (как фильтрует дашборд по issued_at__date),
    # иначе у полуночи возможен off-by-one между UTC и локальной датой.
    day = timezone.localtime(issued).date().isoformat()
    r = cargo_admin_client.get(f"/api/manage/dashboard/?from={day}&to={day}")
    assert r.status_code == 200
    assert r.data["period"]["key"] == "custom"
    assert r.data["period_issued_count"] == 1
    assert r.data["period_revenue_usd"] == 7.0


@pytest.mark.django_db
def test_admin_overview_requires_superuser(cargo_admin_client):
    response = cargo_admin_client.get("/api/admin/overview/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_overview_returns_totals_and_per_cargo(superuser_client):
    client = UserFactory()
    cargo = client.cargo
    PickupPointFactory(cargo=cargo)
    ParcelFactory(user=client, cargo=cargo)

    response = superuser_client.get("/api/admin/overview/")
    assert response.status_code == 200

    totals = response.data["totals"]
    assert totals["cargo_count"] >= 1
    assert totals["user_count"] >= 1
    assert totals["parcel_count"] >= 1
    assert totals["pickup_point_count"] >= 1

    item = next(c for c in response.data["per_cargo"] if c["id"] == cargo.id)
    assert item["users_count"] == 1
    assert item["parcels_count"] == 1
    assert item["pickup_points_count"] >= 1
