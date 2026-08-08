import io

import pytest

from parcels.imports import import_parcels_from_csv
from parcels.models import Parcel, ParcelStatusHistory
from tests.factories import ParcelFactory


@pytest.mark.django_db
def test_parcels_list_filters_to_owner(auth_client):
    parcel = ParcelFactory(user=auth_client.user)
    ParcelFactory()  # another user's parcel
    response = auth_client.get("/api/parcels/")
    assert response.status_code == 200
    items = (
        response.data["results"]
        if isinstance(response.data, dict) and "results" in response.data
        else response.data
    )
    track_numbers = [item["track_number"] for item in items]
    assert parcel.track_number in track_numbers
    assert len(items) == 1


def _items(response):
    d = response.data
    return d["results"] if isinstance(d, dict) and "results" in d else d


@pytest.mark.django_db
def test_pickup_bound_operator_sees_only_own_pickup(api_client):
    from rest_framework_simplejwt.tokens import RefreshToken

    from tests.factories import CargoCompanyFactory, PickupPointFactory, UserFactory

    cargo = CargoCompanyFactory()
    pp1 = PickupPointFactory(cargo=cargo)
    pp2 = PickupPointFactory(cargo=cargo)
    client1 = UserFactory(cargo=cargo, pickup_point=pp1)
    client2 = UserFactory(cargo=cargo, pickup_point=pp2)
    p1 = ParcelFactory(user=client1, cargo=cargo)
    ParcelFactory(user=client2, cargo=cargo)  # чужой ПВЗ

    # Оператор, привязанный к pp1.
    operator = UserFactory(cargo=cargo, is_staff=True, pickup_point=pp1, allowed_tabs=["warehouse"])
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(operator).access_token}"
    )
    r = api_client.get("/api/parcels/")
    tracks = [i["track_number"] for i in _items(r)]
    assert tracks == [p1.track_number]


@pytest.mark.django_db
def test_pickup_bound_operator_sees_unclaimed_received_parcel(api_client):
    """«Ничья» посылка (без клиента), принятая в ПВЗ оператора, видна на его складе."""
    from rest_framework_simplejwt.tokens import RefreshToken

    from parcels.services import scan_parcel
    from tests.factories import CargoCompanyFactory, PickupPointFactory, UserFactory

    cargo = CargoCompanyFactory()
    pp1 = PickupPointFactory(cargo=cargo)
    operator = UserFactory(
        cargo=cargo, is_staff=True, pickup_point=pp1, allowed_tabs=["warehouse"]
    )

    # Приём «ничьей» посылки (без клиента/заказа) в ПВЗ оператора.
    _, parcel = scan_parcel(
        "44",
        cargo=cargo,
        actor=operator,
        status=Parcel.Status.AT_PICKUP_POINT,
    )
    assert parcel.user_id is None
    assert parcel.pickup_point_id == pp1.id

    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(operator).access_token}"
    )
    r = api_client.get("/api/parcels/")
    tracks = [i["track_number"] for i in _items(r)]
    assert "44" in tracks

    # Переключатель прислал чужой ПВЗ — для привязанного оператора игнорируется.
    other = PickupPointFactory(cargo=cargo)
    r = api_client.get(f"/api/parcels/?pickup_point={other.id}")
    tracks = [i["track_number"] for i in _items(r)]
    assert "44" in tracks


@pytest.mark.django_db
def test_bound_operator_receives_into_own_pickup_ignoring_switcher():
    """Привязанный оператор принимает в свой ПВЗ, даже если фронт прислал чужой."""
    from parcels.services import scan_parcel
    from tests.factories import CargoCompanyFactory, PickupPointFactory, UserFactory

    cargo = CargoCompanyFactory()
    own = PickupPointFactory(cargo=cargo)
    other = PickupPointFactory(cargo=cargo)
    operator = UserFactory(cargo=cargo, is_staff=True, pickup_point=own)

    # Фронт прислал pickup_point чужого ПВЗ — должен быть проигнорирован.
    _, parcel = scan_parcel(
        "11",
        cargo=cargo,
        actor=operator,
        status=Parcel.Status.AT_PICKUP_POINT,
        pickup_point=other.id,
    )
    assert parcel.pickup_point_id == own.id


@pytest.mark.django_db
def test_warehouse_filters_status_search_pending(cargo_admin_client):
    from tests.factories import UserFactory

    cargo = cargo_admin_client.user.cargo
    client = UserFactory(cargo=cargo)
    at_pickup = ParcelFactory(
        user=client, cargo=cargo, status=Parcel.Status.AT_PICKUP_POINT,
        track_number="WH-PICKUP-1",
    )
    ParcelFactory(user=client, cargo=cargo, status=Parcel.Status.ISSUED, track_number="WH-ISSUED-1")
    pending = Parcel.objects.create(cargo=cargo, track_number="WH-PENDING-1")

    # status_in
    r = cargo_admin_client.get(
        "/api/parcels/?status_in=at_pickup_point,arrived_kyrgyzstan"
    )
    codes = [i["track_number"] for i in _items(r)]
    assert at_pickup.track_number in codes
    assert "WH-ISSUED-1" not in codes

    # search по треку
    r = cargo_admin_client.get("/api/parcels/?search=WH-PICKUP")
    assert [i["track_number"] for i in _items(r)] == ["WH-PICKUP-1"]

    # pending — только без клиента
    r = cargo_admin_client.get("/api/parcels/?pending=true")
    codes = [i["track_number"] for i in _items(r)]
    assert pending.track_number in codes
    assert at_pickup.track_number not in codes


@pytest.mark.django_db
def test_parcel_serializer_exposes_client_details(cargo_admin_client):
    from tests.factories import UserFactory

    cargo = cargo_admin_client.user.cargo
    client = UserFactory(cargo=cargo, full_name="Иван Клиент")
    ParcelFactory(user=client, cargo=cargo, track_number="WH-DETAIL-1")

    r = cargo_admin_client.get("/api/parcels/?search=WH-DETAIL-1")
    item = _items(r)[0]
    assert item["client_name"] == "Иван Клиент"
    assert item["client_phone"] == client.phone
    assert "pickup_point_title" in item


@pytest.mark.django_db
def test_parcels_filter_by_client_code(auth_client):
    cc = auth_client.user.client_code
    mine = ParcelFactory(user=auth_client.user, client_code=cc)
    ParcelFactory(user=auth_client.user, client_code="C0000001")  # другой код
    response = auth_client.get(f"/api/parcels/?client_code={cc}")
    assert response.status_code == 200
    items = (
        response.data["results"]
        if isinstance(response.data, dict) and "results" in response.data
        else response.data
    )
    tracks = [i["track_number"] for i in items]
    assert mine.track_number in tracks
    assert all(i["client_code"] == cc for i in items)


@pytest.mark.django_db
def test_parcel_history_records_status_change(auth_client):
    parcel = ParcelFactory(user=auth_client.user)
    parcel.status = Parcel.Status.AT_PICKUP_POINT
    parcel.save(update_fields=("status", "updated_at"))

    response = auth_client.get(f"/api/parcels/{parcel.id}/history/")
    assert response.status_code == 200
    statuses = [row["status"] for row in response.data]
    assert Parcel.Status.AT_PICKUP_POINT in statuses


@pytest.mark.django_db
def test_status_timestamps_set(auth_client):
    from parcels.services import update_parcel_status

    parcel = ParcelFactory(user=auth_client.user)
    assert parcel.arrived_at is None and parcel.issued_at is None

    update_parcel_status(parcel, Parcel.Status.ARRIVED_KYRGYZSTAN)
    parcel.refresh_from_db()
    assert parcel.arrived_at is not None
    arrived_at = parcel.arrived_at

    update_parcel_status(parcel, Parcel.Status.ISSUED)
    parcel.refresh_from_db()
    assert parcel.issued_at is not None
    # arrived_at is not overwritten on later transitions.
    assert parcel.arrived_at == arrived_at


@pytest.mark.django_db
def test_csv_import_rejects_owner_reassignment(user):
    from tests.factories import UserFactory

    other = UserFactory()
    ParcelFactory(user=user, track_number="DUP123")
    csv_content = (
        "track_number,client_code,status\n"
        f"DUP123,{other.client_code},purchased\n"
    ).encode("utf-8")
    result = import_parcels_from_csv(io.BytesIO(csv_content))
    assert result.updated == 0
    assert result.skipped == 1
    assert any("принадлежит другому" in err for err in result.errors)
    assert Parcel.objects.get(track_number="DUP123").user_id == user.id


@pytest.mark.django_db
def test_csv_import_creates_parcels(user):
    csv_content = (
        "track_number,client_code,status,location,weight\n"
        f"AAA111,{user.client_code},purchased,Guangzhou,2.5\n"
        f"BBB222,{user.client_code},sent_to_kyrgyzstan,,1.0\n"
    ).encode("utf-8")
    result = import_parcels_from_csv(io.BytesIO(csv_content))
    assert result.created == 2
    assert result.errors == []
    assert Parcel.objects.filter(track_number="AAA111", status="purchased").exists()


@pytest.mark.django_db
def test_csv_import_reports_unknown_client(user):
    csv_content = (
        "track_number,client_code,status\n"
        "XXX999,C9999999,purchased\n"
    ).encode("utf-8")
    result = import_parcels_from_csv(io.BytesIO(csv_content))
    assert result.created == 0
    assert result.skipped == 1
    assert any("не найден" in err for err in result.errors)


# --- Маркетплейс у посылки: мобилка фильтрует по нему ----------------------


@pytest.mark.django_db
def test_parcel_exposes_marketplace_source(auth_client):
    """Клиент должен видеть, с какого маркетплейса посылка."""
    from orders.models import Order

    order = Order.objects.create(
        user=auth_client.user, source=Order.Source.TAOBAO, external_order_id="TB-SRC"
    )
    ParcelFactory(user=auth_client.user, order=order, track_number="SRC-TB")
    # Посылка со сканера — заказа нет вовсе.
    ParcelFactory(user=auth_client.user, order=None, track_number="SRC-SCAN")

    rows = {p["track_number"]: p for p in auth_client.get("/api/parcels/").data}
    assert rows["SRC-TB"]["source"] == "taobao"
    assert rows["SRC-TB"]["source_display_name"] == "Taobao"
    # Без заказа посылка считается заведённой вручную, а не выпадает из ответа.
    assert rows["SRC-SCAN"]["source"] == "manual"


@pytest.mark.django_db
def test_parcels_filter_by_marketplace(auth_client):
    from orders.models import Order

    tb = Order.objects.create(
        user=auth_client.user, source=Order.Source.TAOBAO, external_order_id="F-TB"
    )
    pdd = Order.objects.create(
        user=auth_client.user, source=Order.Source.PINDUODUO, external_order_id="F-PDD"
    )
    ParcelFactory(user=auth_client.user, order=tb, track_number="F-TRACK-TB")
    ParcelFactory(user=auth_client.user, order=pdd, track_number="F-TRACK-PDD")
    ParcelFactory(user=auth_client.user, order=None, track_number="F-TRACK-SCAN")

    def tracks(query):
        return {p["track_number"] for p in auth_client.get(f"/api/parcels/?{query}").data}

    assert tracks("source=taobao") == {"F-TRACK-TB"}
    assert tracks("source=pinduoduo") == {"F-TRACK-PDD"}
    # «Вручную» включает и посылки со сканера, у которых заказа нет.
    assert tracks("source=manual") == {"F-TRACK-SCAN"}
    assert tracks("source_in=taobao,pinduoduo") == {"F-TRACK-TB", "F-TRACK-PDD"}
    # Без фильтра — все, ничего не теряется.
    assert tracks("") >= {"F-TRACK-TB", "F-TRACK-PDD", "F-TRACK-SCAN"}
