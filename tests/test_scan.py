from decimal import Decimal

import pytest

from orders.models import Order
from parcels.models import Parcel
from tests.factories import OrderFactory, ParcelFactory, UserFactory


@pytest.mark.django_db
def test_scan_unknown_track_creates_pending(cargo_admin_client):
    response = cargo_admin_client.post(
        "/api/parcels/scan/", {"track_number": "NEWTRACK001"}, format="json"
    )
    assert response.status_code == 201
    assert response.data["result"] == "created_pending"
    parcel = Parcel.objects.get(track_number="NEWTRACK001")
    assert parcel.user_id is None
    assert parcel.cargo_id == cargo_admin_client.user.cargo_id
    assert parcel.status == Parcel.Status.ARRIVED_CHINA_WAREHOUSE


@pytest.mark.django_db
def test_scan_existing_parcel_advances_status(cargo_admin_client):
    cargo = cargo_admin_client.user.cargo
    client = UserFactory(cargo=cargo)
    parcel = ParcelFactory(user=client, cargo=cargo, status=Parcel.Status.CREATED)

    response = cargo_admin_client.post(
        "/api/parcels/scan/", {"track_number": parcel.track_number}, format="json"
    )
    assert response.status_code == 200
    assert response.data["result"] == "updated"
    parcel.refresh_from_db()
    assert parcel.status == Parcel.Status.ARRIVED_CHINA_WAREHOUSE
    assert parcel.history.filter(status=Parcel.Status.ARRIVED_CHINA_WAREHOUSE).exists()


@pytest.mark.django_db
def test_scan_does_not_move_status_backward(cargo_admin_client):
    # Посылка уже «Прибыл в КР»; повторный скан на складе Китая не откатывает.
    cargo = cargo_admin_client.user.cargo
    parcel = ParcelFactory(cargo=cargo, status=Parcel.Status.ARRIVED_KYRGYZSTAN)
    r = cargo_admin_client.post(
        "/api/parcels/scan/",
        {"track_number": parcel.track_number, "status": Parcel.Status.ARRIVED_CHINA_WAREHOUSE},
        format="json",
    )
    assert r.status_code == 409
    assert r.data["code"] == "already_advanced"
    parcel.refresh_from_db()
    assert parcel.status == Parcel.Status.ARRIVED_KYRGYZSTAN


@pytest.mark.django_db
def test_scan_same_status_is_noop(cargo_admin_client):
    cargo = cargo_admin_client.user.cargo
    parcel = ParcelFactory(cargo=cargo, status=Parcel.Status.ARRIVED_CHINA_WAREHOUSE)
    before = parcel.history.count()
    r = cargo_admin_client.post(
        "/api/parcels/scan/",
        {"track_number": parcel.track_number, "status": Parcel.Status.ARRIVED_CHINA_WAREHOUSE},
        format="json",
    )
    assert r.status_code == 200
    assert r.data["result"] == "unchanged"
    parcel.refresh_from_db()
    assert parcel.status == Parcel.Status.ARRIVED_CHINA_WAREHOUSE
    # Повторный скан не плодит записи в истории.
    assert parcel.history.count() == before


@pytest.mark.django_db
def test_scan_matches_order(cargo_admin_client):
    cargo = cargo_admin_client.user.cargo
    client = UserFactory(cargo=cargo)
    order = OrderFactory(user=client, track_number="ORDTRACK001")

    response = cargo_admin_client.post(
        "/api/parcels/scan/", {"track_number": "ORDTRACK001"}, format="json"
    )
    assert response.status_code == 201
    assert response.data["result"] == "created_from_order"
    parcel = Parcel.objects.get(track_number="ORDTRACK001")
    assert parcel.user_id == client.id
    assert parcel.order_id == order.id


@pytest.mark.django_db
def test_scan_sets_weight_and_computes_price(cargo_admin_client):
    cargo = cargo_admin_client.user.cargo
    cargo.price_per_kg_kgs = Decimal("3.50")
    cargo.save(update_fields=["price_per_kg_kgs"])
    client = UserFactory(cargo=cargo)
    parcel = ParcelFactory(user=client, cargo=cargo, status=Parcel.Status.CREATED)

    response = cargo_admin_client.post(
        "/api/parcels/scan/",
        {
            "track_number": parcel.track_number,
            "status": Parcel.Status.ARRIVED_KYRGYZSTAN,
            "weight": "2",
        },
        format="json",
    )
    assert response.status_code == 200
    parcel.refresh_from_db()
    assert parcel.weight == Decimal("2.000")
    # 2 кг × $3.50 = $7.00
    assert parcel.delivery_price == Decimal("7.00")


@pytest.mark.django_db
def test_weight_endpoint_recalculates_price(cargo_admin_client):
    cargo = cargo_admin_client.user.cargo
    cargo.price_per_kg_kgs = Decimal("3")
    cargo.save(update_fields=["price_per_kg_kgs"])
    client = UserFactory(cargo=cargo)
    parcel = ParcelFactory(
        user=client, cargo=cargo, status=Parcel.Status.AT_PICKUP_POINT,
        weight=None, delivery_price=None, track_number="WGT-END-1",
    )

    r = cargo_admin_client.post(
        f"/api/parcels/{parcel.id}/weight/", {"weight": "2.5"}, format="json"
    )
    assert r.status_code == 200
    parcel.refresh_from_db()
    assert parcel.weight == Decimal("2.500")
    assert parcel.delivery_price == Decimal("7.50")  # 2.5 × $3

    # Очистка веса (null) обнуляет стоимость.
    r = cargo_admin_client.post(
        f"/api/parcels/{parcel.id}/weight/", {"weight": None}, format="json"
    )
    assert r.status_code == 200
    parcel.refresh_from_db()
    assert parcel.weight is None
    assert parcel.delivery_price is None


@pytest.mark.django_db
def test_weight_endpoint_requires_manager(auth_client):
    """Обычный клиент не может менять вес чужой/своей посылки через этот эндпоинт."""
    parcel = ParcelFactory(user=auth_client.user, cargo=auth_client.user.cargo)
    r = auth_client.post(
        f"/api/parcels/{parcel.id}/weight/", {"weight": "1"}, format="json"
    )
    assert r.status_code == 403


@pytest.mark.django_db
def test_scan_cross_cargo_conflict(cargo_admin_client):
    other_parcel = ParcelFactory()  # parcel in a different cargo
    response = cargo_admin_client.post(
        "/api/parcels/scan/",
        {"track_number": other_parcel.track_number},
        format="json",
    )
    assert response.status_code == 409
    assert response.data["code"] == "conflict"


@pytest.mark.django_db
def test_china_staff_scan_restricted_to_china_statuses(api_client, cargo):
    from rest_framework_simplejwt.tokens import RefreshToken

    china = UserFactory(cargo=cargo, is_staff=True, is_china_staff=True)
    client = UserFactory(cargo=cargo)
    OrderFactory(user=client, track_number="CN-OK-1")
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(china).access_token}"
    )

    # Китайский статус — разрешён (карго определяется по заказу).
    ok = api_client.post(
        "/api/parcels/scan/",
        {"track_number": "CN-OK-1", "status": Parcel.Status.ARRIVED_CHINA_WAREHOUSE},
        format="json",
    )
    assert ok.status_code == 201, ok.data
    assert Parcel.objects.get(track_number="CN-OK-1").status == Parcel.Status.ARRIVED_CHINA_WAREHOUSE

    # Выдача — запрещена оператору Китая (проверяется до разбора заказа).
    bad = api_client.post(
        "/api/parcels/scan/",
        {"track_number": "CN-BAD-1", "status": Parcel.Status.ISSUED},
        format="json",
    )
    assert bad.status_code == 403
    assert bad.data["code"] == "forbidden_status"
    assert not Parcel.objects.filter(track_number="CN-BAD-1").exists()


@pytest.mark.django_db
def test_china_staff_global_resolves_cargo_from_order(api_client):
    from rest_framework_simplejwt.tokens import RefreshToken

    from tests.factories import CargoCompanyFactory

    cargo_a = CargoCompanyFactory()  # карго China-оператора (для логина)
    cargo_b = CargoCompanyFactory()  # карго клиента
    china = UserFactory(cargo=cargo_a, is_staff=True, is_china_staff=True)
    client_b = UserFactory(cargo=cargo_b)
    order = OrderFactory(user=client_b, track_number="GLOB-1")

    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(china).access_token}"
    )
    r = api_client.post(
        "/api/parcels/scan/",
        {"track_number": "GLOB-1", "status": Parcel.Status.ARRIVED_CHINA_WAREHOUSE},
        format="json",
    )
    assert r.status_code == 201, r.data
    parcel = Parcel.objects.get(track_number="GLOB-1")
    # Карго определилось по заказу клиента (B), а не по карго оператора (A).
    assert parcel.cargo_id == cargo_b.id
    assert parcel.user_id == client_b.id
    assert parcel.order_id == order.id


@pytest.mark.django_db
def test_china_staff_track_without_anything_creates_unclaimed(api_client, cargo):
    from rest_framework_simplejwt.tokens import RefreshToken

    china = UserFactory(cargo=cargo, is_staff=True, is_china_staff=True)
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(china).access_token}"
    )
    # Трек «без ничего»: ни заказа, ни кода — принимается как ничья посылка.
    r = api_client.post(
        "/api/parcels/scan/",
        {"track_number": "NOORDER-1", "status": Parcel.Status.ARRIVED_CHINA_WAREHOUSE},
        format="json",
    )
    assert r.status_code == 201, r.data
    assert r.data["result"] == "created_pending"
    parcel = Parcel.objects.get(track_number="NOORDER-1")
    assert parcel.cargo_id is None
    assert parcel.user_id is None


@pytest.mark.django_db
def test_cargo_operator_adopts_unclaimed_parcel(cargo_admin_client):
    # Ничья посылка со склада Китая, потом её принимает оператор карго.
    cargo = cargo_admin_client.user.cargo
    client = UserFactory(cargo=cargo)
    orphan = Parcel.objects.create(track_number="ORPHAN-1", cargo=None)

    # Оператор карго сканирует — посылка усыновляется в его карго.
    r = cargo_admin_client.post(
        "/api/parcels/scan/",
        {"track_number": "ORPHAN-1", "status": Parcel.Status.ARRIVED_KYRGYZSTAN},
        format="json",
    )
    assert r.status_code == 200, r.data
    orphan.refresh_from_db()
    assert orphan.cargo_id == cargo.id

    # Привязка клиента по коду.
    r2 = cargo_admin_client.post(
        f"/api/parcels/{orphan.id}/assign/",
        {"client_code": client.client_code},
        format="json",
    )
    assert r2.status_code == 200, r2.data
    orphan.refresh_from_db()
    assert orphan.user_id == client.id


@pytest.mark.django_db
def test_china_staff_manual_by_client_code(api_client):
    from rest_framework_simplejwt.tokens import RefreshToken

    from tests.factories import CargoCompanyFactory

    cargo_a = CargoCompanyFactory()  # карго оператора Китая
    cargo_b = CargoCompanyFactory()  # карго клиента
    china = UserFactory(cargo=cargo_a, is_staff=True, is_china_staff=True)
    client_b = UserFactory(cargo=cargo_b)  # получит client_code

    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(china).access_token}"
    )
    # Заказа нет, но клиент подписал коробку своим кодом → ручной приём.
    r = api_client.post(
        "/api/parcels/scan/",
        {
            "track_number": "MANUAL-1",
            "status": Parcel.Status.ARRIVED_CHINA_WAREHOUSE,
            "client_code": client_b.client_code,
        },
        format="json",
    )
    assert r.status_code == 201, r.data
    assert r.data["result"] == "created_manual"
    parcel = Parcel.objects.get(track_number="MANUAL-1")
    assert parcel.cargo_id == cargo_b.id  # карго определилось по коду клиента
    assert parcel.user_id == client_b.id
    assert parcel.order_id is None
    assert parcel.client_code == client_b.client_code


@pytest.mark.django_db
def test_china_staff_manual_unknown_client_code(api_client, cargo):
    from rest_framework_simplejwt.tokens import RefreshToken

    china = UserFactory(cargo=cargo, is_staff=True, is_china_staff=True)
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(china).access_token}"
    )
    r = api_client.post(
        "/api/parcels/scan/",
        {"track_number": "MANUAL-X", "client_code": "C0000000", "status": Parcel.Status.ARRIVED_CHINA_WAREHOUSE},
        format="json",
    )
    assert r.status_code == 400
    assert r.data["code"] == "no_client"


@pytest.mark.django_db
def test_scan_at_pickup_sets_location_from_client_pickup(cargo_admin_client):
    from tests.factories import PickupPointFactory

    cargo = cargo_admin_client.user.cargo
    pp = PickupPointFactory(cargo=cargo, title="ПВЗ Центр", address="Бишкек, Чуй 100")
    client = UserFactory(cargo=cargo, pickup_point=pp)
    parcel = ParcelFactory(user=client, cargo=cargo, status=Parcel.Status.ARRIVED_KYRGYZSTAN)

    r = cargo_admin_client.post(
        "/api/parcels/scan/",
        {"track_number": parcel.track_number, "status": Parcel.Status.AT_PICKUP_POINT},
        format="json",
    )
    assert r.status_code == 200, r.data
    parcel.refresh_from_db()
    assert parcel.status == Parcel.Status.AT_PICKUP_POINT
    assert parcel.location == "Бишкек, Чуй 100"


@pytest.mark.django_db
def test_scan_at_pickup_uses_explicit_pickup_point(cargo_admin_client):
    from tests.factories import PickupPointFactory

    cargo = cargo_admin_client.user.cargo
    pp = PickupPointFactory(cargo=cargo, address="Ош, Курманжан Датка 12")
    client = UserFactory(cargo=cargo)  # без своего ПВЗ

    r = cargo_admin_client.post(
        "/api/parcels/scan/",
        {
            "track_number": "PP-EXPLICIT-1",
            "status": Parcel.Status.AT_PICKUP_POINT,
            "client_code": client.client_code,
            "pickup_point": pp.id,
        },
        format="json",
    )
    assert r.status_code == 201, r.data
    parcel = Parcel.objects.get(track_number="PP-EXPLICIT-1")
    assert parcel.location == "Ош, Курманжан Датка 12"


@pytest.mark.django_db
def test_scan_forbidden_for_client(auth_client):
    response = auth_client.post(
        "/api/parcels/scan/", {"track_number": "NEWTRACK002"}, format="json"
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_assign_pending_parcel_to_client(cargo_admin_client):
    cargo = cargo_admin_client.user.cargo
    client = UserFactory(cargo=cargo)
    parcel = Parcel.objects.create(cargo=cargo, track_number="PENDING001")

    response = cargo_admin_client.post(
        f"/api/parcels/{parcel.id}/assign/",
        {"client_code": client.client_code},
        format="json",
    )
    assert response.status_code == 200
    parcel.refresh_from_db()
    assert parcel.user_id == client.id
    assert parcel.client_code == client.client_code


@pytest.mark.django_db
def test_assign_unknown_client_code(cargo_admin_client):
    cargo = cargo_admin_client.user.cargo
    parcel = Parcel.objects.create(cargo=cargo, track_number="PENDING002")
    response = cargo_admin_client.post(
        f"/api/parcels/{parcel.id}/assign/",
        {"client_code": "C0000001"},
        format="json",
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_pending_parcel_not_visible_to_client(auth_client):
    parcel = Parcel.objects.create(
        cargo=auth_client.user.cargo, track_number="PENDING003"
    )
    response = auth_client.get("/api/parcels/")
    items = (
        response.data["results"]
        if isinstance(response.data, dict) and "results" in response.data
        else response.data
    )
    assert parcel.track_number not in [i["track_number"] for i in items]
