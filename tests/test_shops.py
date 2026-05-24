import pytest

from shops.models import Shop


@pytest.mark.django_db
def test_shops_list_includes_open_url_with_client_code(auth_client, shop):
    response = auth_client.get("/api/shops/")
    assert response.status_code == 200
    payload = response.data
    items = payload["results"] if isinstance(payload, dict) and "results" in payload else payload
    assert items
    item = items[0]
    assert auth_client.user.client_code in item["open_url"]


@pytest.mark.django_db
def test_shop_clipboard_strategy(auth_client):
    shop = Shop.objects.create(
        cargo=auth_client.user.cargo,
        title="Taobao",
        slug="taobao",
        url="https://taobao.com",
        client_code_strategy=Shop.ClientCodeStrategy.CLIPBOARD,
    )
    response = auth_client.get(f"/api/shops/{shop.id}/")
    assert response.status_code == 200
    assert response.data["client_code"] == auth_client.user.client_code


@pytest.mark.django_db
def test_inactive_shop_hidden(auth_client):
    Shop.objects.create(
        cargo=auth_client.user.cargo,
        title="Hidden",
        slug="hidden",
        url="https://example.com",
        is_active=False,
    )
    response = auth_client.get("/api/shops/")
    items = (
        response.data["results"]
        if isinstance(response.data, dict) and "results" in response.data
        else response.data
    )
    assert all(item["title"] != "Hidden" for item in items)
