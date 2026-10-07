"""Доставка по городу, переработка: точки, заявка на клиента, предложения, бесплатно.

Карго просило четыре вещи: точки выдачи из справочника, а не из кода
приложения; одна заявка на клиента, а не на каждую посылку (курьер ездил по
разу на посылку — у одного клиента на проде было 18 активных заявок); заявку
можно оформить заранее, пока посылок нет; доставка бесплатная. Плюс
предложенные клиентами точки — отдельно и со статистикой.

Обратная совместимость держится тестами: parcel в единственном числе, address,
price и tariff_title живут в установленных версиях приложения.
"""

from decimal import Decimal

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from city_delivery.models import CityDeliveryPoint, CityDeliveryRequest
from parcels.models import Parcel
from tests.factories import (
    CargoCompanyFactory,
    CityDeliveryTariffFactory,
    ParcelFactory,
    UserFactory,
)

REQ = "/api/city-delivery/"
POINTS = "/api/city-delivery-points/"
M_POINTS = "/api/manage/city-delivery-points/"
M_REQ = "/api/manage/city-delivery/"
WHO = {"recipient_name": "Иванов Иван", "recipient_phone": "+996700000001"}

Status = CityDeliveryRequest.Status


def _as(user):
    """Отдельный клиент на пользователя — фикстура api_client в conftest общая."""
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    api.user = user
    return api


def _items(r):
    return r.data["results"] if isinstance(r.data, dict) and "results" in r.data else r.data


@pytest.fixture
def client_api(user):
    return _as(user)


@pytest.fixture
def admin_api(cargo_admin):
    return _as(cargo_admin)


@pytest.fixture
def point(cargo):
    return CityDeliveryPoint.objects.create(
        cargo=cargo, title="Круговой Ак-Тилек, чайхана Ала-Тоо", work_hours="09:00–18:00"
    )


def _parcel(user, status=Parcel.Status.AT_PICKUP_POINT, weight="0.600"):
    return ParcelFactory(user=user, cargo=user.cargo, status=status, weight=Decimal(weight))


# --- §1 справочник точек: клиенту ---


@pytest.mark.django_db
def test_client_sees_active_points_of_own_cargo_only(client_api, cargo, point):
    CityDeliveryPoint.objects.create(cargo=cargo, title="Закрытая", is_active=False)
    CityDeliveryPoint.objects.create(cargo=CargoCompanyFactory(), title="Чужая")

    r = client_api.get(POINTS)
    assert r.status_code == 200
    assert [p["title"] for p in _items(r)] == [point.title]
    assert set(_items(r)[0]) >= {"id", "title", "address", "work_hours", "is_active", "clients_count"}


@pytest.mark.django_db
def test_point_has_no_price(client_api, point):
    """Доставка бесплатная — у точки цены нет и быть не должно."""
    assert "price" not in _items(client_api.get(POINTS))[0]


# --- §1 справочник точек: панель ---


@pytest.mark.django_db
def test_manager_creates_point_in_own_cargo(admin_api, cargo):
    r = admin_api.post(M_POINTS, {"title": "Жаны базар", "work_hours": "10–18"}, format="json")
    assert r.status_code == 201, r.data
    assert CityDeliveryPoint.objects.get(title="Жаны базар").cargo_id == cargo.id


@pytest.mark.django_db
def test_manager_list_carries_stats(admin_api, user, point):
    """Три числа рядом с точкой — чтобы карго понимало, куда возить (§4)."""
    other = UserFactory(cargo=user.cargo)
    CityDeliveryRequest.objects.create(user=user, delivery_point=point, **WHO)
    CityDeliveryRequest.objects.create(user=other, delivery_point=point, **WHO)
    CityDeliveryRequest.objects.create(
        user=other, delivery_point=point, status=Status.DELIVERED, **WHO
    )

    row = next(p for p in _items(admin_api.get(M_POINTS)) if p["id"] == point.id)
    assert row["clients_count"] == 2
    assert row["active_requests"] == 2
    assert row["delivered_count"] == 1


@pytest.mark.django_db
def test_deleting_used_point_deactivates_it(admin_api, user, point):
    """Удаление точки с заявками не должно ломать их историю."""
    CityDeliveryRequest.objects.create(user=user, delivery_point=point, **WHO)

    r = admin_api.delete(f"{M_POINTS}{point.id}/")
    assert r.status_code == 200
    point.refresh_from_db()
    assert point.is_active is False


@pytest.mark.django_db
def test_deleting_unused_point_removes_it(admin_api, point):
    r = admin_api.delete(f"{M_POINTS}{point.id}/")
    assert r.status_code == 204
    assert not CityDeliveryPoint.objects.filter(pk=point.id).exists()


@pytest.mark.django_db
def test_other_cargo_cannot_touch_our_points(point):
    stranger = _as(UserFactory(cargo=CargoCompanyFactory(), is_cargo_admin=True))
    assert stranger.patch(f"{M_POINTS}{point.id}/", {"title": "x"}, format="json").status_code == 404


@pytest.mark.django_db
def test_client_cannot_manage_points(client_api):
    assert client_api.post(M_POINTS, {"title": "x"}, format="json").status_code == 403


# --- §2 заявка: создание ---


@pytest.mark.django_db
def test_request_without_parcels_is_standing(client_api, point):
    """Оформить заранее, пока посылок нет: «всё моё везите сюда»."""
    r = client_api.post(REQ, {"delivery_point": point.id, **WHO}, format="json")
    assert r.status_code == 201, r.data
    assert r.data["is_standing"] is True
    assert r.data["parcels"] == []
    assert r.data["parcels_count"] == 0
    assert r.data["delivery_point_title"] == point.title
    assert r.data["status"] == Status.CREATED


@pytest.mark.django_db
def test_request_with_several_parcels_is_one_request(client_api, user, point):
    a, b = _parcel(user, weight="0.600"), _parcel(user, weight="0.140")

    r = client_api.post(
        REQ, {"delivery_point": point.id, "parcels": [a.id, b.id], **WHO}, format="json"
    )
    assert r.status_code == 201, r.data
    assert r.data["is_standing"] is False
    assert r.data["parcels_count"] == 2
    assert r.data["total_weight_kg"] == "0.740"
    first = r.data["parcels"][0]
    assert set(first) >= {"id", "track_number", "status", "status_display_name", "weight"}
    assert CityDeliveryRequest.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_legacy_single_parcel_still_works(client_api, user):
    """Установленные версии шлют parcel и address — ломать их нельзя."""
    p = _parcel(user)
    r = client_api.post(
        REQ, {"parcel": p.id, "address": "Бишкек, Чуй 1", **WHO}, format="json"
    )
    assert r.status_code == 201, r.data
    assert [x["id"] for x in r.data["parcels"]] == [p.id]
    assert r.data["parcel"] == p.id
    assert r.data["track_number"] == p.track_number
    assert r.data["address"] == "Бишкек, Чуй 1"


@pytest.mark.django_db
def test_suggested_point_is_accepted(client_api):
    r = client_api.post(
        REQ, {"suggested_point": "Ошский рынок, вход с Кулатова", **WHO}, format="json"
    )
    assert r.status_code == 201, r.data
    assert r.data["delivery_point"] is None
    assert r.data["suggested_point"] == "Ошский рынок, вход с Кулатова"


@pytest.mark.django_db
def test_destination_is_required(client_api):
    r = client_api.post(REQ, {**WHO}, format="json")
    assert r.status_code == 400
    assert "куда" in str(r.data).lower()


@pytest.mark.django_db
def test_point_of_another_cargo_is_rejected(client_api):
    foreign = CityDeliveryPoint.objects.create(cargo=CargoCompanyFactory(), title="Чужая")
    r = client_api.post(REQ, {"delivery_point": foreign.id, **WHO}, format="json")
    assert r.status_code == 400


@pytest.mark.django_db
def test_inactive_point_is_rejected(client_api, cargo):
    closed = CityDeliveryPoint.objects.create(cargo=cargo, title="Закрыта", is_active=False)
    r = client_api.post(REQ, {"delivery_point": closed.id, **WHO}, format="json")
    assert r.status_code == 400


@pytest.mark.django_db
def test_foreign_parcel_is_rejected(client_api, point):
    r = client_api.post(
        REQ, {"delivery_point": point.id, "parcels": [ParcelFactory().id], **WHO}, format="json"
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_issued_parcel_is_rejected(client_api, user, point):
    p = _parcel(user, status=Parcel.Status.ISSUED)
    r = client_api.post(
        REQ, {"delivery_point": point.id, "parcels": [p.id], **WHO}, format="json"
    )
    assert r.status_code == 400


# --- §2 одна заявка на клиента ---


@pytest.mark.django_db
def test_second_post_updates_the_live_request(client_api, user, cargo, point):
    other_point = CityDeliveryPoint.objects.create(cargo=cargo, title="Жаны базар")
    first = client_api.post(REQ, {"delivery_point": point.id, **WHO}, format="json")

    again = client_api.post(
        REQ,
        {"delivery_point": other_point.id, "recipient_name": "Петров", "recipient_phone": "+996700000002"},
        format="json",
    )
    assert again.status_code == 200, again.data
    assert again.data["id"] == first.data["id"]
    assert again.data["delivery_point"] == other_point.id
    assert again.data["recipient_name"] == "Петров"
    assert CityDeliveryRequest.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_post_while_courier_is_on_the_way_is_409(client_api, user, point):
    """Менять точку, когда курьер уже едет, нельзя — отдаём id, приложение покажет заявку."""
    req = CityDeliveryRequest.objects.create(
        user=user, delivery_point=point, status=Status.IN_DELIVERY, **WHO
    )
    r = client_api.post(REQ, {"delivery_point": point.id, **WHO}, format="json")
    assert r.status_code == 409
    assert r.data["id"] == req.id


@pytest.mark.django_db
def test_client_can_change_point_with_patch(client_api, user, cargo, point):
    other_point = CityDeliveryPoint.objects.create(cargo=cargo, title="Анар")
    req = CityDeliveryRequest.objects.create(user=user, delivery_point=point, **WHO)

    r = client_api.patch(f"{REQ}{req.id}/", {"delivery_point": other_point.id}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["delivery_point"] == other_point.id


@pytest.mark.django_db
def test_client_can_cancel(client_api, user, point):
    req = CityDeliveryRequest.objects.create(user=user, delivery_point=point, **WHO)

    r = client_api.post(f"{REQ}{req.id}/cancel/")
    assert r.status_code == 200, r.data
    assert r.data["status"] == Status.CANCELLED

    fresh = client_api.post(REQ, {"delivery_point": point.id, **WHO}, format="json")
    assert fresh.status_code == 201
    assert fresh.data["id"] != req.id


@pytest.mark.django_db
def test_client_cannot_cancel_after_courier_took_it(client_api, user, point):
    req = CityDeliveryRequest.objects.create(
        user=user, delivery_point=point, status=Status.IN_DELIVERY, **WHO
    )
    assert client_api.post(f"{REQ}{req.id}/cancel/").status_code == 409


# --- §2 постоянная заявка подхватывает посылки ---


@pytest.mark.django_db
def test_standing_request_takes_parcels_already_in_pickup(client_api, user, point):
    waiting = _parcel(user)
    _parcel(user, status=Parcel.Status.IN_TRANSIT)  # ещё едет — не берём

    r = client_api.post(REQ, {"delivery_point": point.id, **WHO}, format="json")
    assert [p["id"] for p in r.data["parcels"]] == [waiting.id]


@pytest.mark.django_db
def test_parcel_arriving_later_joins_standing_request(client_api, user, point):
    r = client_api.post(REQ, {"delivery_point": point.id, **WHO}, format="json")
    p = _parcel(user, status=Parcel.Status.CUSTOMS)

    from parcels.services import update_parcel_status

    update_parcel_status(p, Parcel.Status.AT_PICKUP_POINT)

    req = CityDeliveryRequest.objects.get(pk=r.data["id"])
    assert list(req.parcels.values_list("id", flat=True)) == [p.id]


@pytest.mark.django_db
def test_parcel_assigned_to_client_in_pickup_joins_standing_request(client_api, user, point):
    """Ничья посылка в ПВЗ нашла хозяина — она тоже должна уехать к нему."""
    r = client_api.post(REQ, {"delivery_point": point.id, **WHO}, format="json")
    p = Parcel.objects.create(
        cargo=user.cargo, track_number="ORPHAN-1", status=Parcel.Status.AT_PICKUP_POINT
    )
    p.user = user
    p.save()

    req = CityDeliveryRequest.objects.get(pk=r.data["id"])
    assert p.id in req.parcels.values_list("id", flat=True)


@pytest.mark.django_db
def test_parcel_does_not_join_request_already_on_the_road(user, point):
    req = CityDeliveryRequest.objects.create(
        user=user, delivery_point=point, is_standing=True, status=Status.IN_DELIVERY, **WHO
    )
    _parcel(user)
    assert req.parcels.count() == 0


# --- §5 бесплатно ---


@pytest.mark.django_db
def test_price_is_zero_without_tariff(client_api, user, point):
    p = _parcel(user, weight="3.000")
    r = client_api.post(
        REQ, {"delivery_point": point.id, "parcels": [p.id], **WHO}, format="json"
    )
    assert r.data["price"] == "0.00"
    assert "tariff_title" in r.data


@pytest.mark.django_db
def test_estimate_returns_zero_and_works_without_parcel(client_api, user):
    assert client_api.post(f"{REQ}estimate/", {}, format="json").data["price"] == Decimal("0")
    p = _parcel(user)
    assert client_api.post(f"{REQ}estimate/", {"parcel": p.id}, format="json").data["price"] == Decimal("0")


@pytest.mark.django_db
def test_cargo_tariff_still_prices_by_total_weight(client_api, user, point):
    """Бесплатно — это отсутствие тарифа, а не запрет: карго может завести свой."""
    CityDeliveryTariffFactory(
        cargo=user.cargo, base_price="100", price_per_kg="10", free_weight_kg="0"
    )
    a, b = _parcel(user, weight="1.000"), _parcel(user, weight="2.000")
    r = client_api.post(
        REQ, {"delivery_point": point.id, "parcels": [a.id, b.id], **WHO}, format="json"
    )
    assert r.data["price"] == "130.00"


# --- §3 предложенные точки ---


@pytest.mark.django_db
def test_manage_filter_suggested(admin_api, user, point):
    wanted = CityDeliveryRequest.objects.create(user=user, suggested_point="Ош базар", **WHO)
    CityDeliveryRequest.objects.create(
        user=UserFactory(cargo=user.cargo), delivery_point=point, **WHO
    )

    ids = [x["id"] for x in _items(admin_api.get(f"{M_REQ}?suggested=true"))]
    assert ids == [wanted.id]


@pytest.mark.django_db
def test_assigning_point_clears_suggestion(admin_api, user, point):
    req = CityDeliveryRequest.objects.create(user=user, suggested_point="Ош базар", **WHO)

    r = admin_api.patch(f"{M_REQ}{req.id}/", {"delivery_point": point.id}, format="json")
    assert r.status_code == 200, r.data
    req.refresh_from_db()
    assert req.delivery_point_id == point.id
    assert req.suggested_point == ""


@pytest.mark.django_db
def test_suggestions_are_grouped_and_counted(admin_api, user):
    a, b = user, UserFactory(cargo=user.cargo)
    for who, text in [
        (a, "Ошский рынок, вход с Кулатова"),
        (a, "  ошский   рынок, вход с кулатова "),
        (b, "Ошский рынок, вход с Кулатова"),
        (b, "Микрорайон Анар, дом 14"),
    ]:
        CityDeliveryRequest.objects.create(user=who, suggested_point=text, **WHO)
    CityDeliveryRequest.objects.create(
        user=UserFactory(cargo=CargoCompanyFactory()), suggested_point="Ошский рынок, вход с Кулатова", **WHO
    )

    r = admin_api.get(f"{M_POINTS}suggestions/")
    assert r.status_code == 200, r.data
    top = r.data[0]
    assert top["text"] == "Ошский рынок, вход с Кулатова"
    assert top["clients_count"] == 2
    assert top["requests_count"] == 3
    assert len(top["request_ids"]) == 3
    assert {"first_seen", "last_seen"} <= set(top)
    assert r.data[1]["clients_count"] == 1


@pytest.mark.django_db
def test_cancelled_requests_are_not_in_suggestions(admin_api, user):
    CityDeliveryRequest.objects.create(
        user=user, suggested_point="Ош базар", status=Status.CANCELLED, **WHO
    )
    assert admin_api.get(f"{M_POINTS}suggestions/").data == []


@pytest.mark.django_db
def test_adopt_suggestions_moves_all_matching_requests(admin_api, user, point):
    for text in ["Ош базар", "ОШ  базар", "Другое место"]:
        CityDeliveryRequest.objects.create(user=user, suggested_point=text, **WHO)

    r = admin_api.post(
        f"{M_POINTS}{point.id}/adopt-suggestions/", {"text": "ош базар"}, format="json"
    )
    assert r.status_code == 200, r.data
    assert r.data["updated"] == 2
    assert CityDeliveryRequest.objects.filter(delivery_point=point).count() == 2
    assert CityDeliveryRequest.objects.filter(suggested_point="Другое место").exists()


@pytest.mark.django_db
def test_dashboard_counts_unprocessed_suggestions(admin_api, user, point):
    CityDeliveryRequest.objects.create(user=user, suggested_point="Ош базар", **WHO)
    CityDeliveryRequest.objects.create(user=user, delivery_point=point, **WHO)
    CityDeliveryRequest.objects.create(
        user=user, suggested_point="Готово", status=Status.DELIVERED, **WHO
    )

    r = admin_api.get("/api/manage/dashboard/")
    assert r.status_code == 200, r.data
    assert r.data["suggested_points_count"] == 1


# --- панель: статусы и ответ ---


@pytest.mark.django_db
def test_delivered_marks_every_parcel_delivered(admin_api, user, point):
    a, b = _parcel(user), _parcel(user)
    req = CityDeliveryRequest.objects.create(user=user, delivery_point=point, **WHO)
    req.parcels.set([a, b])

    r = admin_api.patch(f"{M_REQ}{req.id}/", {"status": Status.DELIVERED}, format="json")
    assert r.status_code == 200, r.data
    a.refresh_from_db()
    b.refresh_from_db()
    assert a.status == b.status == Parcel.Status.DELIVERED


@pytest.mark.django_db
def test_in_delivery_moves_every_parcel(admin_api, user, point):
    a, b = _parcel(user), _parcel(user)
    req = CityDeliveryRequest.objects.create(user=user, delivery_point=point, **WHO)
    req.parcels.set([a, b])

    admin_api.patch(f"{M_REQ}{req.id}/", {"status": Status.IN_DELIVERY}, format="json")
    a.refresh_from_db()
    assert a.status == Parcel.Status.CITY_DELIVERY


@pytest.mark.django_db
def test_standing_request_reopens_after_delivery(admin_api, user, point):
    """Клиент сказал «куда» один раз — следующая партия поедет туда же."""
    req = CityDeliveryRequest.objects.create(
        user=user, delivery_point=point, is_standing=True, **WHO
    )
    req.parcels.set([_parcel(user)])

    admin_api.patch(f"{M_REQ}{req.id}/", {"status": Status.DELIVERED}, format="json")

    reopened = CityDeliveryRequest.objects.exclude(pk=req.id).get(user=user)
    assert reopened.is_standing is True
    assert reopened.delivery_point_id == point.id
    assert reopened.status == Status.CREATED
    assert reopened.parcels.count() == 0


@pytest.mark.django_db
def test_manage_response_shape(admin_api, user, point):
    p = _parcel(user)
    req = CityDeliveryRequest.objects.create(user=user, delivery_point=point, **WHO)
    req.parcels.set([p])

    row = next(x for x in _items(admin_api.get(M_REQ)) if x["id"] == req.id)
    for key in (
        "client_code", "client_name", "client_phone", "delivery_point",
        "delivery_point_title", "suggested_point", "address", "is_standing",
        "parcels", "parcels_count", "total_weight_kg", "price", "tariff_title",
        "status", "status_display_name",
    ):
        assert key in row, key
    assert row["parcels_count"] == 1


@pytest.mark.django_db
def test_manage_filter_has_parcels(admin_api, user, point):
    """Пустая постоянная заявка — не работа для курьера; её можно спрятать."""
    empty = CityDeliveryRequest.objects.create(user=user, delivery_point=point, is_standing=True, **WHO)
    full = CityDeliveryRequest.objects.create(
        user=UserFactory(cargo=user.cargo), delivery_point=point, **WHO
    )
    full.parcels.set([_parcel(full.user)])

    ids = [x["id"] for x in _items(admin_api.get(f"{M_REQ}?has_parcels=true"))]
    assert ids == [full.id]
    assert empty.id not in ids


# --- заведение шести точек ---


@pytest.mark.django_db
def test_seed_command_creates_six_points_once(cargo):
    from django.core.management import call_command

    call_command("seed_city_delivery_points", "--cargo", str(cargo.id))
    call_command("seed_city_delivery_points", "--cargo", str(cargo.id))

    titles = list(CityDeliveryPoint.objects.filter(cargo=cargo).values_list("title", flat=True))
    assert len(titles) == 6
    assert titles[0] == "Круговой Ак-Тилек, чайхана Ала-Тоо"
