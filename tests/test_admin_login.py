import pytest
from django.contrib.auth import get_user_model

from tests.factories import UserFactory

User = get_user_model()


@pytest.mark.django_db
def test_admin_login_superuser_by_phone(client):
    User.objects.create_superuser(phone="+996700999999", password="secret123")

    response = client.post(
        "/admin/login/",
        {
            "username": "+996700999999",
            "password": "secret123",
            "next": "/admin/",
        },
    )

    assert response.status_code == 302
    assert response.url == "/admin/"


@pytest.mark.django_db
def test_admin_login_cargo_admin_by_phone(client):
    user = UserFactory(phone="+996700888888", password="adminpass")
    user.is_cargo_admin = True
    user.save()

    response = client.post(
        "/admin/login/",
        {
            "username": user.phone,
            "password": "adminpass",
            "next": "/admin/",
        },
    )

    assert response.status_code == 302
    assert response.url == "/admin/"


@pytest.mark.django_db
def test_admin_login_rejects_client(client):
    UserFactory(phone="+996700777777", password="clientpass")

    response = client.post(
        "/admin/login/",
        {
            "username": "+996700777777",
            "password": "clientpass",
            "next": "/admin/",
        },
    )

    assert response.status_code == 200
    assert "Неверный телефон или пароль" in response.content.decode()


@pytest.mark.django_db
def test_admin_login_page_shows_phone_label(client):
    response = client.get("/admin/login/")

    assert response.status_code == 200
    assert "Телефон" in response.content.decode()
    assert "Ключ входа" not in response.content.decode()


@pytest.mark.django_db
def test_admin_sms_code_list_shows_code(client):
    User.objects.create_superuser(phone="+996700999999", password="secret123")
    client.post(
        "/admin/login/",
        {
            "username": "+996700999999",
            "password": "secret123",
            "next": "/admin/",
        },
    )

    from datetime import timedelta

    from django.utils import timezone

    from users.models import SMSCode

    SMSCode.objects.create(
        phone="+996700111111",
        code="1234",
        purpose=SMSCode.Purpose.LOGIN,
        expires_at=timezone.now() + timedelta(minutes=5),
    )

    response = client.get("/admin/users/smscode/")

    assert response.status_code == 200
    content = response.content.decode()
    assert "1234" in content
    assert "+996700111111" in content

