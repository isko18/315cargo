import logging
import threading
from typing import Iterable

from django.conf import settings

from .models import (
    DeviceToken,
    Notification,
    NotificationPreference,
    NotificationType,
)

logger = logging.getLogger(__name__)

_firebase_lock = threading.Lock()
_firebase_initialized = False

# Канал Android создаётся приложением; шлём в него же, иначе на закрытом
# приложении уведомление уходит в безымянную «Разное» без звука.
ANDROID_CHANNEL_ID = "cargo315_default"


def _ensure_firebase_initialized():
    global _firebase_initialized
    if _firebase_initialized:
        return True
    with _firebase_lock:
        if _firebase_initialized:
            return True
        credentials_path = getattr(settings, "FCM_CREDENTIALS_PATH", "") or ""
        if not credentials_path:
            return False
        try:
            import firebase_admin
            from firebase_admin import credentials

            if not firebase_admin._apps:
                cred = credentials.Certificate(credentials_path)
                firebase_admin.initialize_app(cred)
            _firebase_initialized = True
            return True
        except Exception as exc:
            logger.exception("Failed to initialize Firebase: %s", exc)
            return False


def get_or_create_preference(user) -> NotificationPreference:
    preference, _ = NotificationPreference.objects.get_or_create(user=user)
    return preference


def _is_allowed(user, notification_type) -> bool:
    preference = get_or_create_preference(user)
    if not preference.push_enabled:
        return False
    return preference.allows(notification_type)


def create_notification(user, title, body, type=NotificationType.SYSTEM, data=None):
    notification = Notification.objects.create(
        user=user,
        title=title,
        body=body,
        type=type,
        data=data or {},
    )
    return notification


def _active_tokens(user) -> list[str]:
    """Все живые токены пользователя: телефон + планшет + переустановки."""
    return list(
        DeviceToken.objects.filter(user=user, is_active=True).values_list(
            "token", flat=True
        )
    )


def unread_count(user) -> int:
    """Счётчик непрочитанных — им же красим бейдж на iOS (сам он не считает)."""
    return Notification.objects.filter(user=user, is_read=False).count()


def _token_is_dead(exc) -> bool:
    """Токен мёртв навсегда или это временный сбой FCM?

    Гасим только безнадёжные: приложение удалено, токен отозван (клиент делает
    ``deleteToken()`` при выходе) или битый. Временные ошибки (UNAVAILABLE,
    INTERNAL, превышение квоты) токен не портят — на них гасить нельзя, иначе
    после каждого сбоя FCM пользователи молча перестают получать пуши.
    """
    if exc is None:
        return False
    from firebase_admin import exceptions as fb_exceptions
    from firebase_admin import messaging

    return isinstance(
        exc,
        (
            messaging.UnregisteredError,
            messaging.SenderIdMismatchError,
            fb_exceptions.InvalidArgumentError,
            fb_exceptions.NotFoundError,
        ),
    )


def send_push_notification(
    user,
    title: str,
    body: str,
    data: dict | None = None,
    type: str = NotificationType.SYSTEM,
) -> bool:
    if not _is_allowed(user, type):
        logger.info(
            "Push skipped by preferences",
            extra={"user_id": user.id, "type": type},
        )
        return False

    tokens = _active_tokens(user)
    if not tokens:
        logger.info("No active device tokens", extra={"user_id": user.id})
        return False

    # FCM принимает только строковые значения в data.
    payload = {k: str(v) for k, v in (data or {}).items()}
    # Тип кладём всегда: мобилка роутит tap по нему (parcel → экран посылки).
    payload.setdefault("type", str(type))

    if not _ensure_firebase_initialized():
        logger.info(
            "Mock push notification (no FCM credentials)",
            extra={
                "user_id": user.id,
                "title": title,
                "tokens_count": len(tokens),
                "data": payload,
            },
        )
        return True

    try:
        from firebase_admin import messaging

        message = messaging.MulticastMessage(
            tokens=tokens,
            # Блок notification обязателен: только data-сообщения на закрытом
            # iOS не показываются вообще.
            notification=messaging.Notification(title=title, body=body),
            data=payload,
            android=messaging.AndroidConfig(
                # Без HIGH доставку откладывает Doze на десятки минут.
                priority="high",
                notification=messaging.AndroidNotification(
                    channel_id=ANDROID_CHANNEL_ID, sound="default"
                ),
            ),
            apns=messaging.APNSConfig(
                headers={"apns-priority": "10"},
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(sound="default", badge=unread_count(user))
                ),
            ),
        )
        response = messaging.send_each_for_multicast(message)
    except Exception as exc:
        logger.exception("FCM send failed: %s", exc)
        return False

    dead_tokens = []
    for idx, resp in enumerate(response.responses):
        if resp.success:
            continue
        logger.warning(
            "FCM delivery failed",
            extra={"token": tokens[idx], "error": str(resp.exception)},
        )
        if _token_is_dead(resp.exception):
            dead_tokens.append(tokens[idx])
    if dead_tokens:
        DeviceToken.objects.filter(token__in=dead_tokens).update(is_active=False)

    logger.info(
        "FCM push sent",
        extra={
            "user_id": user.id,
            "success": response.success_count,
            "failure": response.failure_count,
        },
    )
    return response.success_count > 0


def notify(
    user,
    title: str,
    body: str,
    type: str = NotificationType.SYSTEM,
    data: dict | None = None,
    push: bool = True,
) -> Notification | None:
    """Create an in-app notification and optionally send push.

    Respects the user's per-category preference (e.g. ``order_status_enabled``,
    ``marketing_enabled``): a disabled category produces neither an in-app
    record nor a push. ``push_enabled`` governs only push delivery, not the
    in-app record (handled in ``send_push_notification``)."""
    preference = get_or_create_preference(user)
    if not preference.allows(type):
        logger.info(
            "Notification skipped by category preference",
            extra={"user_id": user.id, "type": type},
        )
        return None
    notification = create_notification(user, title, body, type=type, data=data)
    if push:
        send_push_notification(user, title, body, data=data, type=type)
    return notification


def notify_many(
    users: Iterable,
    title: str,
    body: str,
    type: str = NotificationType.SYSTEM,
    data: dict | None = None,
    push: bool = True,
) -> int:
    count = 0
    for user in users:
        if notify(user, title, body, type=type, data=data, push=push) is not None:
            count += 1
    return count
