import pytest

from orders.models import Order
from tests.factories import OrderFactory


@pytest.mark.django_db
def test_orders_list_only_owner(auth_client):
    OrderFactory(user=auth_client.user)
    OrderFactory()
    response = auth_client.get("/api/orders/")
    assert response.status_code == 200
    items = (
        response.data["results"]
        if isinstance(response.data, dict) and "results" in response.data
        else response.data
    )
    assert len(items) == 1


@pytest.mark.django_db
def test_create_manual_order(auth_client):
    response = auth_client.post(
        "/api/orders/manual/",
        {
            "product_title": "Test product",
            "product_url": "https://example.com/item",
            "price": "12.34",
            "quantity": 2,
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    order = Order.objects.get(id=response.data["id"])
    assert order.source == Order.Source.MANUAL
    assert order.user == auth_client.user
    assert order.status == Order.Status.CREATED


@pytest.mark.django_db
def test_orders_filter_by_status(auth_client):
    OrderFactory(user=auth_client.user, status=Order.Status.CREATED)
    OrderFactory(user=auth_client.user, status=Order.Status.PAID)
    response = auth_client.get("/api/orders/?status=paid")
    items = (
        response.data["results"]
        if isinstance(response.data, dict) and "results" in response.data
        else response.data
    )
    assert all(item["status"] == "paid" for item in items)
