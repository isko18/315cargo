import pytest


@pytest.mark.django_db
def test_profile_returns_client_code(auth_client):
    response = auth_client.get("/api/profile/")
    assert response.status_code == 200
    assert response.data["client_code"]


@pytest.mark.django_db
def test_profile_qr(auth_client):
    response = auth_client.get("/api/profile/qr/")
    assert response.status_code == 200
    assert response.data["client_code"]
    assert response.data["qr_code_image"]


@pytest.mark.django_db
def test_profile_patch_full_name(auth_client):
    response = auth_client.patch(
        "/api/profile/", {"full_name": "Новое Имя"}, format="json"
    )
    assert response.status_code == 200
    assert response.data["full_name"] == "Новое Имя"
