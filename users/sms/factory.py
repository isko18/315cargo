from django.conf import settings

from .mock import MockSmsBackend
from .nikita import NikitaSmsBackend
from .meta_whatsapp import MetaWhatsAppBackend
from .whatsapp import WahaWhatsAppBackend


def _sms_backend():
    """Бэкенд SMS: явный выбор через SMS_BACKEND, иначе по наличию логина."""
    backend = (getattr(settings, "SMS_BACKEND", "") or "auto").lower()
    if backend == "mock":
        return MockSmsBackend()
    if backend == "nikita":
        return NikitaSmsBackend()
    if settings.NIKITA_SMS_LOGIN and settings.NIKITA_SMS_PASSWORD:
        return NikitaSmsBackend()
    return MockSmsBackend()


def get_sms_backend():
    """Совместимость: часть кода и тестов ждёт именно SMS-бэкенд."""
    return _sms_backend()


def _whatsapp_backend():
    """Канал один — «whatsapp», провайдер под ним меняется переменной.

    Так переход с self-hosted шлюза на Meta не задевает ни OTP_CHANNELS, ни
    приложение: в ответе send-code и в SMSCode.channel по-прежнему "whatsapp".
    """
    provider = (getattr(settings, "WHATSAPP_PROVIDER", "") or "waha").lower()
    if provider == "meta":
        if not (settings.META_WA_PHONE_NUMBER_ID and settings.META_WA_TOKEN):
            return MockSmsBackend()
        return MetaWhatsAppBackend()
    if not settings.WHATSAPP_API_URL:
        # Канал включён, но шлюз не настроен — молча отдаём mock, чтобы разработка
        # и тесты не требовали поднятого WhatsApp.
        return MockSmsBackend()
    return WahaWhatsAppBackend()


CHANNEL_BACKENDS = {
    "whatsapp": _whatsapp_backend,
    "sms": _sms_backend,
}


def get_otp_backends():
    """Каналы доставки OTP по порядку из OTP_CHANNELS.

    Возвращает список пар (имя канала, бэкенд). Порядок значим: первый
    успешно доставивший канал останавливает перебор, поэтому дешёвый WhatsApp
    ставится перед SMS, а не наоборот.
    """
    raw = getattr(settings, "OTP_CHANNELS", "") or "sms"
    names = [part.strip().lower() for part in raw.split(",") if part.strip()]
    backends = []
    for name in names:
        factory = CHANNEL_BACKENDS.get(name)
        if factory is None:
            continue
        backends.append((name, factory()))
    if not backends:
        # Пустой или испорченный OTP_CHANNELS не должен ронять вход целиком.
        backends.append(("sms", _sms_backend()))
    return backends
