"""Отправка OTP через WhatsApp.

Временное решение: self-hosted шлюз WAHA (docker-образ devlikeapro/waha),
который держит сессию обычного аккаунта WhatsApp и отдаёт REST API. Django
ходит в него по localhost — сессия обязана жить в одном процессе, а gunicorn
работает в нескольких воркерах, поэтому шлюз вынесен отдельным сервисом.

Осознанный компромисс: рассылка кодов с обычного аккаунта нарушает правила
WhatsApp, номер могут заблокировать. Поэтому WhatsApp включается только первым
каналом каскада — при любой ошибке код уходит по SMS (см. OTP_CHANNELS).

Меняется на официальный Meta Cloud API заменой этого файла: наружу торчит
только send_otp(), остальному коду всё равно, кто доставил сообщение.
"""

import logging

import requests
from django.conf import settings

from ..constants import OTP_TTL_MINUTES
from .exceptions import SmsBackendError

logger = logging.getLogger(__name__)


def normalize_phone_for_whatsapp(phone: str) -> str:
    """WhatsApp ждёт chatId только из цифр: ни `+`, ни пробелов, ни дефисов."""
    return "".join(ch for ch in str(phone) if ch.isdigit())


def build_otp_text(code: str) -> str:
    """Текст кода для WhatsApp.

    Бренд отдельный от SMS: в NIKITA_SMS_BRAND лежит идентификатор отправителя,
    согласованный с оператором (на проде «SMSPRO.KG»). В SMS он уместен, а в
    WhatsApp клиент увидит незнакомое имя и примет код за фишинг.

    Разметка — WhatsApp-овская: `*` даёт жирный. В SMS её быть не должно, там
    звёздочки покажутся мусором, поэтому у SMS свой build_otp_text.
    """
    brand = getattr(settings, "WHATSAPP_BRAND", "") or "315CARGO"
    return (
        f"*{brand}*\n\n"
        f"Ваш код подтверждения: *{code}*\n\n"
        f"Действителен {OTP_TTL_MINUTES} мин. Никому не сообщайте этот код."
    )


class WahaWhatsAppBackend:
    """Клиент self-hosted шлюза WAHA."""

    provider = "whatsapp"

    def __init__(self, base_url=None, api_key=None, session=None, timeout=None):
        self.base_url = (base_url or settings.WHATSAPP_API_URL).rstrip("/")
        self.api_key = api_key or settings.WHATSAPP_API_KEY
        self.session = session or settings.WHATSAPP_SESSION
        self.timeout = timeout or settings.WHATSAPP_TIMEOUT

    def send_otp(self, phone, code, purpose, message_id):
        if not self.base_url:
            raise SmsBackendError("Не задан WHATSAPP_API_URL")

        chat_id = normalize_phone_for_whatsapp(phone)
        if not chat_id:
            raise SmsBackendError("Некорректный номер телефона для WhatsApp")

        payload = {
            "session": self.session,
            "chatId": f"{chat_id}@c.us",
            "text": build_otp_text(code),
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key

        try:
            response = requests.post(
                f"{self.base_url}/api/sendText",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            # Шлюз не поднят, сессия отвалилась, таймаут — каскад уведёт в SMS.
            logger.warning("WhatsApp gateway unreachable: %s", exc)
            raise SmsBackendError("Шлюз WhatsApp недоступен") from exc

        if response.status_code >= 400:
            # 404/422 здесь — обычно «у номера нет WhatsApp» или сессия не
            # авторизована. Различать не нужно: и то и другое означает «шли SMS».
            provider_message = response.text[:300]
            logger.warning(
                "WhatsApp send rejected",
                extra={
                    "status": response.status_code,
                    "phone": chat_id,
                    "provider_message": provider_message,
                },
            )
            raise SmsBackendError(
                "WhatsApp не принял сообщение",
                status_code=response.status_code,
                provider_message=provider_message,
            )

        try:
            data = response.json()
        except ValueError:
            data = {}

        return {
            "message_id": (data.get("id") or {}).get("id") or data.get("id") or message_id,
            "provider": self.provider,
        }
