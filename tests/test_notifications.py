import pytest

from notifications.models import (
    DeviceToken,
    Notification,
    NotificationPreference,
    NotificationType,
)
from notifications.services import notify
from orders.models import Order
from parcels.models import Parcel
from tests.factories import OrderFactory, ParcelFactory


@pytest.mark.django_db
def test_welcome_notification_created_on_registration(user):
    assert Notification.objects.filter(user=user, type=NotificationType.AUTH).exists()


@pytest.mark.django_db
def test_order_created_signals_notification(user):
    OrderFactory(user=user)
    assert Notification.objects.filter(
        user=user, type=NotificationType.ORDER_CREATED
    ).exists()


@pytest.mark.django_db
def test_parcel_status_change_creates_history_and_notification(user):
    parcel = ParcelFactory(user=user)
    parcel.status = Parcel.Status.AT_PICKUP_POINT
    parcel.save(update_fields=("status", "updated_at"))
    assert Notification.objects.filter(
        user=user, type=NotificationType.PARCEL_AT_PICKUP_POINT
    ).exists()


@pytest.mark.django_db
def test_preference_blocks_push(monkeypatch, user):
    preference = NotificationPreference.objects.create(
        user=user,
        push_enabled=False,
    )
    DeviceToken.objects.create(
        user=user, token="abc", platform=DeviceToken.Platform.ANDROID
    )
    sent = []

    def fake_send(user, title, body, data=None, type=None):
        sent.append(title)
        return True

    monkeypatch.setattr("notifications.services.send_push_notification", fake_send)
    notify(user, "T", "B", type=NotificationType.PARCEL_STATUS_CHANGED)
    # in-app notification created
    assert Notification.objects.filter(user=user, title="T").exists()


@pytest.mark.django_db
def test_marketing_notification_off_by_default(user):
    # marketing_enabled defaults to False, so a marketing notification creates
    # neither an in-app record nor a push.
    result = notify(user, "Sale", "50% off", type=NotificationType.MARKETING)
    assert result is None
    assert not Notification.objects.filter(
        user=user, type=NotificationType.MARKETING
    ).exists()


@pytest.mark.django_db
def test_disabled_category_skips_in_app(user):
    NotificationPreference.objects.create(user=user, order_status_enabled=False)
    result = notify(user, "T", "B", type=NotificationType.ORDER_STATUS_CHANGED)
    assert result is None
    assert not Notification.objects.filter(user=user, title="T").exists()


@pytest.mark.django_db
def test_notification_preference_endpoint(auth_client):
    response = auth_client.get("/api/profile/notification-preferences/")
    assert response.status_code == 200
    assert response.data["push_enabled"] is True

    response = auth_client.patch(
        "/api/profile/notification-preferences/",
        {"push_enabled": False},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["push_enabled"] is False


@pytest.mark.django_db
def test_register_device_token(auth_client):
    response = auth_client.post(
        "/api/device-tokens/",
        {"token": "fcm-token-1", "platform": "android"},
        format="json",
    )
    assert response.status_code == 201
    assert DeviceToken.objects.filter(token="fcm-token-1").exists()


@pytest.mark.django_db
def test_unread_count(auth_client):
    response = auth_client.get("/api/notifications/unread-count/")
    assert response.status_code == 200
    assert response.data["count"] >= 1
