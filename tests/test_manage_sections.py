import pytest

from city_delivery.models import CityDeliveryRequest
from parcels.models import Parcel
from tests.factories import (
    CityDeliveryRequestFactory,
    OrderFactory,
    ParcelFactory,
    UserFactory,
)


def _items(r):
    return r.data["results"] if isinstance(r.data, dict) and "results" in r.data else r.data


@pytest.mark.django_db
def test_clients_list_and_history(cargo_admin_client):
    cargo = cargo_admin_client.user.cargo
    client = UserFactory(cargo=cargo, full_name="Иван Клиент")
    OrderFactory(user=client, product_title="Куртка")
    ParcelFactory(user=client, cargo=cargo)

    r = cargo_admin_client.get("/api/manage/clients/")
    assert r.status_code == 200
    row = next(c for c in _items(r) if c["id"] == client.id)
    assert row["full_name"] == "Иван Клиент"
    assert row["orders_count"] == 1
    assert row["parcels_count"] == 1

    h = cargo_admin_client.get(f"/api/manage/clients/{client.id}/history/")
    assert h.status_code == 200
    assert len(h.data["orders"]) == 1
    assert len(h.data["parcels"]) == 1
    assert h.data["client"]["full_name"] == "Иван Клиент"


@pytest.mark.django_db
def test_clients_scoped_to_cargo(cargo_admin_client):
    cargo = cargo_admin_client.user.cargo
    mine = UserFactory(cargo=cargo)
    other = UserFactory()  # другое карго
    r = cargo_admin_client.get("/api/manage/clients/")
    ids = [c["id"] for c in _items(r)]
    assert mine.id in ids
    assert other.id not in ids


@pytest.mark.django_db
def test_clients_filtered_by_pickup_switcher(cargo_admin_client):
    """Переключатель ПВЗ в шапке должен сужать и список клиентов."""
    from tests.factories import PickupPointFactory

    cargo = cargo_admin_client.user.cargo
    here = PickupPointFactory(cargo=cargo)
    there = PickupPointFactory(cargo=cargo)
    mine = UserFactory(cargo=cargo, pickup_point=here)
    theirs = UserFactory(cargo=cargo, pickup_point=there)

    r = cargo_admin_client.get(f"/api/manage/clients/?pickup_point={here.id}")

    ids = [c["id"] for c in _items(r)]
    assert mine.id in ids
    assert theirs.id not in ids


@pytest.mark.django_db
def test_bound_operator_ignores_pickup_switcher(api_client, cargo):
    """Чужой ПВЗ в параметре не должен ни открывать чужих, ни прятать своих.

    activeId лежит в localStorage и легко оказывается от другого пункта —
    применив его, мы спрятали бы от оператора его же клиентов.
    """
    from rest_framework_simplejwt.tokens import RefreshToken

    from tests.factories import PickupPointFactory

    his = PickupPointFactory(cargo=cargo)
    other = PickupPointFactory(cargo=cargo)
    mine = UserFactory(cargo=cargo, pickup_point=his)
    stranger = UserFactory(cargo=cargo, pickup_point=other)
    op = UserFactory(cargo=cargo, is_staff=True, pickup_point=his, allowed_tabs=["clients"])
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(op).access_token}")

    ids = [c["id"] for c in _items(api_client.get(f"/api/manage/clients/?pickup_point={other.id}"))]

    assert mine.id in ids
    assert stranger.id not in ids


@pytest.mark.django_db
def test_clients_ignore_garbage_pickup_param(cargo_admin_client):
    """Мусор в параметре не должен ронять список."""
    cargo = cargo_admin_client.user.cargo
    mine = UserFactory(cargo=cargo)

    r = cargo_admin_client.get("/api/manage/clients/?pickup_point=abc")

    assert r.status_code == 200
    assert mine.id in [c["id"] for c in _items(r)]


@pytest.mark.django_db
def test_operator_without_clients_tab_forbidden(api_client, cargo):
    from rest_framework_simplejwt.tokens import RefreshToken

    op = UserFactory(cargo=cargo, is_staff=True, allowed_tabs=["warehouse"])
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(op).access_token}")
    assert api_client.get("/api/manage/clients/").status_code == 403


@pytest.mark.django_db
def test_delivery_request_status_update_syncs_parcel(cargo_admin_client):
    cargo = cargo_admin_client.user.cargo
    client = UserFactory(cargo=cargo)
    parcel = ParcelFactory(user=client, cargo=cargo, status=Parcel.Status.AT_PICKUP_POINT)
    req = CityDeliveryRequestFactory(user=client, parcel=parcel)

    r = cargo_admin_client.patch(
        f"/api/manage/city-delivery/{req.id}/",
        {"status": CityDeliveryRequest.Status.DELIVERED},
        format="json",
    )
    assert r.status_code == 200, r.data
    req.refresh_from_db()
    parcel.refresh_from_db()
    assert req.status == CityDeliveryRequest.Status.DELIVERED
    assert req.delivered_at is not None
    assert parcel.status == Parcel.Status.DELIVERED


@pytest.mark.django_db
def test_delivery_requests_scoped_to_cargo(cargo_admin_client):
    cargo = cargo_admin_client.user.cargo
    mine = CityDeliveryRequestFactory(
        user=UserFactory(cargo=cargo),
        parcel=ParcelFactory(cargo=cargo),
    )
    CityDeliveryRequestFactory()  # другое карго
    r = cargo_admin_client.get("/api/manage/city-delivery/")
    ids = [x["id"] for x in _items(r)]
    assert mine.id in ids
    assert len(ids) == 1


@pytest.mark.django_db
def test_city_delivery_filtered_by_pickup_switcher(cargo_admin_client):
    """Заявки на доставку тоже должны сужаться переключателем ПВЗ."""
    from tests.factories import PickupPointFactory

    cargo = cargo_admin_client.user.cargo
    here = PickupPointFactory(cargo=cargo)
    there = PickupPointFactory(cargo=cargo)
    mine = CityDeliveryRequestFactory(user=UserFactory(cargo=cargo, pickup_point=here))
    theirs = CityDeliveryRequestFactory(user=UserFactory(cargo=cargo, pickup_point=there))

    r = cargo_admin_client.get(f"/api/manage/city-delivery/?pickup_point={here.id}")

    ids = [x["id"] for x in _items(r)]
    assert mine.id in ids
    assert theirs.id not in ids


@pytest.mark.django_db
def test_history_filtered_by_pickup_switcher(cargo_admin_client):
    from tests.factories import PickupPointFactory

    cargo = cargo_admin_client.user.cargo
    here = PickupPointFactory(cargo=cargo)
    there = PickupPointFactory(cargo=cargo)
    mine = ParcelFactory(cargo=cargo, pickup_point=here, status="at_pickup_point")
    theirs = ParcelFactory(cargo=cargo, pickup_point=there, status="at_pickup_point")

    r = cargo_admin_client.get(f"/api/history/?pickup_point={here.id}")

    tracks = [x["track_number"] for x in _items(r)]
    assert mine.track_number in tracks
    assert theirs.track_number not in tracks


@pytest.mark.django_db
def test_history_keeps_operations_before_pickup_is_stamped(cargo_admin_client):
    """До приёмки ПВЗ у посылки пуст — берём пункт клиента, иначе операция
    выпала бы из истории своего же ПВЗ."""
    from tests.factories import PickupPointFactory

    cargo = cargo_admin_client.user.cargo
    point = PickupPointFactory(cargo=cargo)
    client = UserFactory(cargo=cargo, pickup_point=point)
    parcel = ParcelFactory(
        cargo=cargo, user=client, pickup_point=None, status="arrived_china_warehouse"
    )

    r = cargo_admin_client.get(f"/api/history/?pickup_point={point.id}")

    assert parcel.track_number in [x["track_number"] for x in _items(r)]
