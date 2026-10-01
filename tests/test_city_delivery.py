from decimal import Decimal

import pytest

from city_delivery.models import CityDeliveryRequest, CityDeliveryTariff
from city_delivery.services import calculate_price
from tests.factories import (
    CityDeliveryTariffFactory,
    ParcelFactory,
)


@pytest.mark.django_db
def test_tariff_calculate_base_only():
    tariff = CityDeliveryTariffFactory(
        base_price=Decimal("100"),
        price_per_kg=Decimal("20"),
        free_weight_kg=Decimal("1"),
    )
    parcel = ParcelFactory(weight=Decimal("0.5"))
    price, used = calculate_price(parcel, tariff)
    assert price == Decimal("100")
    assert used == tariff


@pytest.mark.django_db
def test_tariff_calculate_extra_weight():
    tariff = CityDeliveryTariffFactory(
        base_price=Decimal("100"),
        price_per_kg=Decimal("20"),
        free_weight_kg=Decimal("1"),
    )
    parcel = ParcelFactory(weight=Decimal("3.5"))
    price, _ = calculate_price(parcel, tariff)
    assert price == Decimal("100") + Decimal("2.5") * Decimal("20")


@pytest.mark.django_db
def test_tariff_min_price_applied():
    tariff = CityDeliveryTariffFactory(
        base_price=Decimal("10"),
        price_per_kg=Decimal("0"),
        min_price=Decimal("150"),
    )
    parcel = ParcelFactory(weight=Decimal("0.1"))
    price, _ = calculate_price(parcel, tariff)
    assert price == Decimal("150")


@pytest.mark.django_db
def test_create_city_delivery_request_auto_price(auth_client):
    CityDeliveryTariffFactory(
        base_price=Decimal("100"),
        price_per_kg=Decimal("50"),
        free_weight_kg=Decimal("0"),
        is_default=True,
    )
    parcel = ParcelFactory(user=auth_client.user, weight=Decimal("2"))

    response = auth_client.post(
        "/api/city-delivery/",
        {
            "parcel": parcel.id,
            "address": "Бишкек, Чуй 1",
            "recipient_name": "Test",
            "recipient_phone": "+996700111111",
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    assert response.data["price"] == "200.00"
    assert response.data["status"] == CityDeliveryRequest.Status.PRICE_CALCULATED


@pytest.mark.django_db
def test_estimate_endpoint(auth_client):
    CityDeliveryTariffFactory(
        base_price=Decimal("100"),
        price_per_kg=Decimal("10"),
        free_weight_kg=Decimal("0"),
    )
    parcel = ParcelFactory(user=auth_client.user, weight=Decimal("5"))
    response = auth_client.post(
        "/api/city-delivery/estimate/", {"parcel": parcel.id}, format="json"
    )
    assert response.status_code == 200
    assert response.data["price"] == Decimal("150")


@pytest.mark.django_db
def test_tariff_isolated_to_its_cargo(auth_client):
    from tests.factories import CargoCompanyFactory

    # A general tariff bound to another cargo must NOT price our parcel.
    other_cargo = CargoCompanyFactory()
    CityDeliveryTariffFactory(cargo=other_cargo, is_default=True)
    parcel = ParcelFactory(user=auth_client.user, weight=Decimal("2"))

    price, tariff = calculate_price(parcel)
    assert price is None and tariff is None


@pytest.mark.django_db
def test_cannot_create_for_other_user_parcel(auth_client):
    CityDeliveryTariffFactory()
    foreign_parcel = ParcelFactory()
    response = auth_client.post(
        "/api/city-delivery/",
        {
            "parcel": foreign_parcel.id,
            "address": "X",
            "recipient_name": "X",
            "recipient_phone": "+996700111111",
        },
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_tariff_always_carries_pickup_point_title_key(auth_client):
    """Ключ не должен исчезать у тарифа без ПВЗ.

    DRF при обходе source «pickup_point.title» на пустом ПВЗ выбрасывает поле
    целиком: оно объявлено в схеме, а в ответе его нет. Клиент, читающий
    справочник точек, на таком расхождении спотыкается.
    """
    from city_delivery.models import CityDeliveryTariff

    CityDeliveryTariff.objects.create(
        title="Глобальный", base_price=100, price_per_kg=10,
        free_weight_kg=1, min_price=100, pickup_point=None, cargo=None,
    )

    r = auth_client.get("/api/city-delivery-tariffs/")
    rows = r.data["results"] if isinstance(r.data, dict) else r.data
    assert rows, r.data
    for row in rows:
        assert "pickup_point_title" in row, row
    without_point = [x for x in rows if x["pickup_point"] is None]
    assert without_point
    assert without_point[0]["pickup_point_title"] is None
