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
