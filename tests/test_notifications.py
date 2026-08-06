import pytest

from notifications.models import (
    DeviceToken,
    Notification,
    NotificationPreference,
    NotificationType,
)
from notifications.services import notify, send_push_notification, unread_count
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
def test_push_message_matches_mobile_contract(monkeypatch, user):
    """Мобилка ждёт notification + data + канал Android + бейдж iOS."""
    DeviceToken.objects.create(
        user=user, token="tok-contract", platform=DeviceToken.Platform.ANDROID
    )
    Notification.objects.filter(user=user).update(is_read=False)
    captured = {}

    def fake_multicast(**kwargs):
        captured.update(kwargs)
        return object()

    def fake_send(message):
        class _Resp:
            responses = []
            success_count = 1
            failure_count = 0

        return _Resp()

    from firebase_admin import messaging

    monkeypatch.setattr(
        "notifications.services._ensure_firebase_initialized", lambda: True
    )
    monkeypatch.setattr(messaging, "MulticastMessage", fake_multicast)
    monkeypatch.setattr(messaging, "send_each_for_multicast", fake_send)

    send_push_notification(
        user,
        "Посылка в пути",
        "TRACK1 выехала в Кыргызстан",
        data={"parcel_id": 7},
        type=NotificationType.PARCEL_STATUS_CHANGED,
    )

    # data: только строки, type кладётся всегда — по нему мобилка роутит tap.
    assert captured["data"]["type"] == NotificationType.PARCEL_STATUS_CHANGED
    assert captured["data"]["parcel_id"] == "7"  # FCM не принимает числа
    assert captured["notification"] is not None  # без него iOS молчит
    assert captured["android"].priority == "high"  # иначе Doze тормозит доставку
    assert captured["android"].notification.channel_id == "cargo315_default"
    assert captured["apns"].headers["apns-priority"] == "10"
    assert captured["apns"].payload.aps.badge == unread_count(user)


@pytest.mark.django_db
def test_only_dead_tokens_are_deactivated(monkeypatch, user):
    """Временный сбой FCM не должен гасить рабочий токен."""
    from firebase_admin import exceptions as fb_exceptions
    from firebase_admin import messaging

    DeviceToken.objects.filter(user=user).delete()
    dead = DeviceToken.objects.create(
        user=user, token="dead", platform=DeviceToken.Platform.ANDROID
    )
    flaky = DeviceToken.objects.create(
        user=user, token="flaky", platform=DeviceToken.Platform.ANDROID
    )

    class _R:
        def __init__(self, exc):
            self.success = exc is None
            self.exception = exc

    def fake_send(message):
        class _Resp:
            # Порядок ответов совпадает с порядком токенов.
            responses = [
                _R(messaging.UnregisteredError("gone")),
                _R(fb_exceptions.UnavailableError("try later", cause=None)),
            ]
            success_count = 0
            failure_count = 2

        return _Resp()

    monkeypatch.setattr(
        "notifications.services._ensure_firebase_initialized", lambda: True
    )
    monkeypatch.setattr(messaging, "send_each_for_multicast", fake_send)
    monkeypatch.setattr(
        "notifications.services._active_tokens", lambda u: ["dead", "flaky"]
    )

    send_push_notification(
        user, "T", "B", type=NotificationType.PARCEL_STATUS_CHANGED
    )

    dead.refresh_from_db()
    flaky.refresh_from_db()
    assert dead.is_active is False
    assert flaky.is_active is True


@pytest.mark.django_db
def test_unregister_device_token_on_logout(auth_client):
    auth_client.post(
        "/api/device-tokens/", {"token": "bye-1", "platform": "android"}, format="json"
    )
    assert DeviceToken.objects.filter(token="bye-1").exists()

    response = auth_client.delete(
        "/api/device-tokens/", {"token": "bye-1"}, format="json"
    )
    assert response.status_code == 204
    assert not DeviceToken.objects.filter(token="bye-1").exists()

    # Повторный выход не должен падать.
    assert (
        auth_client.delete(
            "/api/device-tokens/", {"token": "bye-1"}, format="json"
        ).status_code
        == 204
    )


@pytest.mark.django_db
def test_unregister_requires_token(auth_client):
    response = auth_client.delete("/api/device-tokens/", {}, format="json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_unregister_does_not_touch_other_users_token(auth_client, staff_user):
    DeviceToken.objects.create(
        user=staff_user, token="not-mine", platform=DeviceToken.Platform.ANDROID
    )
    response = auth_client.delete(
        "/api/device-tokens/", {"token": "not-mine"}, format="json"
    )
    assert response.status_code == 204
    assert DeviceToken.objects.filter(token="not-mine").exists()


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
