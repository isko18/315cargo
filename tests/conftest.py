import pytest
from django.test import override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from .factories import CargoCompanyFactory, PickupPointFactory, ShopFactory, UserFactory


@pytest.fixture(autouse=True)
def mock_sms_backend():
    with override_settings(SMS_BACKEND="mock"):
        yield


@pytest.fixture(autouse=True)
def isolate_test_media(tmp_path, settings):
    media_root = tmp_path / "media"
    media_root.mkdir(exist_ok=True)
    settings.MEDIA_ROOT = media_root


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def cargo(db):
    return CargoCompanyFactory()


@pytest.fixture
def pickup_point(db, cargo):
    return PickupPointFactory(cargo=cargo)


@pytest.fixture
def user(db, pickup_point):
    return UserFactory(pickup_point=pickup_point, cargo=pickup_point.cargo)


@pytest.fixture
def staff_user(db, pickup_point):
    return UserFactory(pickup_point=pickup_point, cargo=pickup_point.cargo, is_staff=True)


@pytest.fixture
def auth_client(api_client, user):
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    api_client.user = user
    return api_client


@pytest.fixture
def staff_client(api_client, staff_user):
    refresh = RefreshToken.for_user(staff_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    api_client.user = staff_user
    return api_client


@pytest.fixture
def cargo_admin(db, pickup_point):
    return UserFactory(
        pickup_point=pickup_point, cargo=pickup_point.cargo, is_cargo_admin=True
    )


@pytest.fixture
def cargo_admin_client(api_client, cargo_admin):
    refresh = RefreshToken.for_user(cargo_admin)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    api_client.user = cargo_admin
    return api_client


@pytest.fixture
def superuser(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_superuser(
        phone="+996700999999", password="secret123"
    )


@pytest.fixture
def superuser_client(api_client, superuser):
    refresh = RefreshToken.for_user(superuser)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    api_client.user = superuser
    return api_client


@pytest.fixture
def shop(db, user):
    return ShopFactory(cargo=user.cargo)
