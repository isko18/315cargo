from django.conf import settings

from .mock import MockSmsBackend
from .nikita import NikitaSmsBackend


def get_sms_backend():
    backend = (getattr(settings, "SMS_BACKEND", "") or "auto").lower()
    if backend == "mock":
        return MockSmsBackend()
    if backend == "nikita":
        return NikitaSmsBackend()
    if settings.NIKITA_SMS_LOGIN and settings.NIKITA_SMS_PASSWORD:
        return NikitaSmsBackend()
    return MockSmsBackend()
