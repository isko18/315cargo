import pytest

from parcels.models import Parcel


def _op(cargo, actor, status, track, user=None, price=None):
    """Посылка + запись истории с оператором (как при скане: сигнал пишет
    ParcelStatusHistory с changed_by = _status_changed_by)."""
    p = Parcel(cargo=cargo, user=user, track_number=track, status=status, delivery_price=price)
    p._status_changed_by = actor
    p.save()
    return p


@pytest.mark.django_db
def test_history_operator_sees_only_own(api_client, cargo_admin):
    from rest_framework_simplejwt.tokens import RefreshToken
    from tests.factories import UserFactory

    cargo = cargo_admin.cargo
    op1 = UserFactory(cargo=cargo, is_staff=True, allowed_tabs=["history"])
    op2 = UserFactory(cargo=cargo, is_staff=True)
    _op(cargo, op1, Parcel.Status.AT_PICKUP_POINT, "H-OP1-REC")
    _op(cargo, op1, Parcel.Status.ISSUED, "H-OP1-ISS", price="5.00")
    _op(cargo, op2, Parcel.Status.AT_PICKUP_POINT, "H-OP2-REC")

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(op1).access_token}")
    r = api_client.get("/api/history/")
    assert r.status_code == 200
    tracks = {row["track_number"] for row in r.data}
    assert tracks == {"H-OP1-REC", "H-OP1-ISS"}
    assert "H-OP2-REC" not in tracks


@pytest.mark.django_db
def test_history_manager_sees_all_and_filters(cargo_admin_client):
    from tests.factories import UserFactory

    cargo = cargo_admin_client.user.cargo
    op1 = UserFactory(cargo=cargo, is_staff=True)
    op2 = UserFactory(cargo=cargo, is_staff=True)
    _op(cargo, op1, Parcel.Status.AT_PICKUP_POINT, "M-REC-1")
    _op(cargo, op1, Parcel.Status.ISSUED, "M-ISS-1", price="7.00")
    _op(cargo, op2, Parcel.Status.AT_PICKUP_POINT, "M-REC-2")

    # Админ карго видит всё по карго.
    r = cargo_admin_client.get("/api/history/")
    tracks = {row["track_number"] for row in r.data}
    assert {"M-REC-1", "M-ISS-1", "M-REC-2"} <= tracks

    # Фильтр по типу.
    r = cargo_admin_client.get("/api/history/?type=issue")
    types = {row["type"] for row in r.data}
    assert types == {"issue"}

    # Фильтр по оператору.
    r = cargo_admin_client.get(f"/api/history/?operator={op2.id}")
    tracks = {row["track_number"] for row in r.data}
    assert tracks == {"M-REC-2"}


@pytest.mark.django_db
def test_history_cargo_scoped(cargo_admin_client):
    from tests.factories import CargoCompanyFactory, UserFactory

    cargo = cargo_admin_client.user.cargo
    other = CargoCompanyFactory()
    op_other = UserFactory(cargo=other, is_staff=True)
    _op(other, op_other, Parcel.Status.ISSUED, "OTHER-ISS", price="9.00")

    r = cargo_admin_client.get("/api/history/")
    tracks = {row["track_number"] for row in r.data}
    assert "OTHER-ISS" not in tracks
