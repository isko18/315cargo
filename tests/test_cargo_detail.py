import pytest

from parcels.models import Parcel


@pytest.mark.django_db
def test_cargo_detail_super_only(cargo_admin, superuser):
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken

    def client_for(user):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
        return c

    cargo_id = cargo_admin.cargo_id
    # Админ карго — не супер: 403.
    r = client_for(cargo_admin).get(f"/api/admin/cargos/{cargo_id}/detail/")
    assert r.status_code == 403
    # Супер — 200.
    r = client_for(superuser).get(f"/api/admin/cargos/{cargo_id}/detail/")
    assert r.status_code == 200


@pytest.mark.django_db
def test_cargo_detail_warehouse_and_staff(superuser_client, cargo_admin):
    from tests.factories import PickupPointFactory, UserFactory

    cargo = cargo_admin.cargo
    pp = PickupPointFactory(cargo=cargo)
    client = UserFactory(cargo=cargo, pickup_point=pp)
    operator = UserFactory(cargo=cargo, is_staff=True, pickup_point=pp)

    # На складе pp: одна принятая (at_pickup_point), одна выданная.
    Parcel.objects.create(
        cargo=cargo, user=client, pickup_point=pp, track_number="CD-AT-1",
        status=Parcel.Status.AT_PICKUP_POINT,
    )
    Parcel.objects.create(
        cargo=cargo, user=client, pickup_point=pp, track_number="CD-ISS-1",
        status=Parcel.Status.ISSUED, is_archived=True, delivery_price="5.00",
    )

    r = superuser_client.get(f"/api/admin/cargos/{cargo.id}/detail/")
    assert r.status_code == 200
    d = r.data

    assert d["cargo"]["id"] == cargo.id
    row = next(p for p in d["pickups"] if p["id"] == pp.id)
    assert row["at_warehouse"] == 1
    assert row["issued"] == 1
    assert row["clients"] == 1
    assert row["staff"] == 1

    staff_ids = [s["id"] for s in d["staff"]]
    assert operator.id in staff_ids
    assert d["totals"]["revenue_issued"] == 5.0
