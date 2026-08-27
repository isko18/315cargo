"""Страница привязки WhatsApp.

Главный риск здесь не вёрстка, а доступ: страница ходит в админский API шлюза,
который намеренно закрыт от интернета. Если она откроется постороннему, наружу
утечёт возможность перепривязать чужой номер и читать состояние сессии.
"""

import pytest
from django.test import override_settings

GATEWAY = "http://127.0.0.1:3000"
PAGE = "/admin/whatsapp/"


@pytest.fixture
def staff_not_super(db, pickup_point):
    from tests.factories import UserFactory

    user = UserFactory(pickup_point=pickup_point, cargo=pickup_point.cargo, is_staff=True)
    user.set_password("secret123")
    user.save()
    return user


@pytest.mark.django_db
def test_anonymous_is_redirected_to_login(client):
    response = client.get(PAGE)
    assert response.status_code == 302
    assert "/admin/login" in response["Location"]


@pytest.mark.django_db
def test_staff_without_superuser_is_forbidden(client, staff_not_super):
    """Привязка номера — действие владельца: обычному сотруднику нельзя."""
    client.force_login(staff_not_super)
    assert client.get(PAGE).status_code == 403


@pytest.mark.django_db
@override_settings(WHATSAPP_API_URL=GATEWAY)
def test_superuser_sees_page(client, superuser):
    client.force_login(superuser)
    response = client.get(PAGE)
    assert response.status_code == 200
    assert b"whatsapp" in response.content.lower()


@pytest.mark.django_db
@override_settings(WHATSAPP_API_URL="")
def test_page_warns_when_gateway_not_configured(client, superuser):
    client.force_login(superuser)
    response = client.get(PAGE)
    assert response.status_code == 200
    assert "WHATSAPP_API_URL" in response.content.decode()


@pytest.mark.django_db
@override_settings(WHATSAPP_API_URL=GATEWAY)
def test_status_reports_gateway_down_instead_of_500(client, superuser, monkeypatch):
    """Упавший контейнер должен показываться на странице, а не ронять её."""
    import requests

    def boom(*args, **kwargs):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr("common.waha.requests.request", boom)
    client.force_login(superuser)

    response = client.get(PAGE + "status/")
    assert response.status_code == 200
    assert response.json()["status"] == "GATEWAY_DOWN"


@pytest.mark.django_db
@override_settings(WHATSAPP_API_URL=GATEWAY)
def test_status_passes_through_connected_number(client, superuser, monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "status": "WORKING",
                "me": {"id": "996700123456@c.us", "pushName": "315CARGO"},
            }

    monkeypatch.setattr("common.waha.requests.request", lambda *a, **kw: FakeResponse())
    client.force_login(superuser)

    data = client.get(PAGE + "status/").json()
    assert data["status"] == "WORKING"
    assert data["phone"] == "996700123456"
    assert data["name"] == "315CARGO"


@pytest.mark.django_db
@override_settings(WHATSAPP_API_URL=GATEWAY)
def test_qr_image_is_proxied(client, superuser, monkeypatch):
    class FakeResponse:
        status_code = 200
        content = b"\x89PNG\r\n\x1a\n"
        headers = {"Content-Type": "image/png"}

    monkeypatch.setattr("common.waha.requests.request", lambda *a, **kw: FakeResponse())
    client.force_login(superuser)

    response = client.get(PAGE + "qr.png")
    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    # QR живёт секунды — закешированная картинка была бы бесполезна.
    assert "no-store" in response["Cache-Control"]


@pytest.mark.django_db
def test_qr_image_requires_superuser(client, staff_not_super):
    client.force_login(staff_not_super)
    assert client.get(PAGE + "qr.png").status_code == 403


@pytest.mark.django_db
def test_restart_requires_superuser(client, staff_not_super):
    client.force_login(staff_not_super)
    assert client.post(PAGE + "restart/").status_code == 403


@pytest.mark.django_db
@override_settings(WHATSAPP_API_URL=GATEWAY)
def test_restart_rejects_get(client, superuser):
    """Перезапуск меняет состояние: он не должен срабатывать переходом по ссылке."""
    client.force_login(superuser)
    assert client.get(PAGE + "restart/").status_code == 405
