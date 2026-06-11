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


@pytest.mark.django_db
def test_profile_patch_rejects_foreign_cargo_pickup_point(auth_client):
    from tests.factories import PickupPointFactory

    foreign_pp = PickupPointFactory()  # belongs to a different cargo
    response = auth_client.patch(
        "/api/profile/", {"pickup_point": foreign_pp.id}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_profile_patch_accepts_own_cargo_pickup_point(auth_client):
    from tests.factories import PickupPointFactory

    own_pp = PickupPointFactory(cargo=auth_client.user.cargo)
    response = auth_client.patch(
        "/api/profile/", {"pickup_point": own_pp.id}, format="json"
    )
    assert response.status_code == 200
    assert response.data["pickup_point"] == own_pp.id
