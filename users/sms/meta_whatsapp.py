"""Отправка OTP через официальный WhatsApp Cloud API (Meta).

В отличие от self-hosted шлюза, здесь нет сессии, которую WhatsApp может
разлогинить: отправка идёт от верифицированного бизнес-номера по одобренному
шаблону категории AUTHENTICATION.

Текст сообщения задать нельзя — он фиксирован Meta и локализован ей же
("*{{1}}* is your verification code" и переводы). Настраиваются только
приписка о безопасности, срок действия в футере и кнопка «скопировать код».
Поэтому build_otp_text здесь нет: мы передаём только сам код.
"""

import logging

import requests
from django.conf import settings

from .exceptions import SmsBackendError

logger = logging.getLogger(__name__)


def normalize_phone(phone: str) -> str:
    """Meta ждёт номер в международном формате без «+» и разделителей."""
    return "".join(ch for ch in str(phone) if ch.isdigit())


class MetaWhatsAppBackend:
    provider = "meta"

    def __init__(self, phone_number_id=None, token=None, template=None, lang=None,
                 api_version=None, timeout=None, button=None):
        self.phone_number_id = phone_number_id or settings.META_WA_PHONE_NUMBER_ID
        self.token = token or settings.META_WA_TOKEN
        self.template = template or settings.META_WA_TEMPLATE
        self.lang = lang or settings.META_WA_LANG
        self.api_version = api_version or settings.META_WA_API_VERSION
        self.timeout = timeout or settings.META_WA_TIMEOUT
        self.button = (button or settings.META_WA_OTP_BUTTON or "url").lower()

    def _button_component(self, code):
        """Кнопка OTP: url (one-tap) или copy_code — задаётся META_WA_OTP_BUTTON."""
        if self.button == "copy_code":
            return {
                "type": "button",
                "sub_type": "COPY_CODE",
                "index": "0",
                "parameters": [{"type": "coupon_code", "coupon_code": code}],
            }
        return {
            "type": "button",
            "sub_type": "url",
            "index": "0",
            "parameters": [{"type": "text", "text": code}],
        }

    def send_otp(self, phone, code, purpose, message_id):
        if not self.phone_number_id or not self.token:
            raise SmsBackendError("Не заданы META_WA_PHONE_NUMBER_ID / META_WA_TOKEN")

        to = normalize_phone(phone)
        if not to:
            raise SmsBackendError("Некорректный номер телефона для WhatsApp")

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "template",
            "template": {
                "name": self.template,
                "language": {"code": self.lang},
                "components": [
                    {"type": "body", "parameters": [{"type": "text", "text": code}]},
                    # Код обязан дублироваться в кнопке — без этого компонента
                    # Meta отклоняет отправку (#132018). Форма зависит от того,
                    # какую кнопку одобрили в шаблоне, и перепутать их нельзя:
                    # на url-шаблон COPY_CODE отвечает «Button at index 0 must
                    # be of type Url», и наоборот.
                    self._button_component(code),
                ],
            },
        }

        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        try:
            response = requests.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            logger.warning("Meta WhatsApp unreachable: %s", exc)
            raise SmsBackendError("Meta WhatsApp недоступен") from exc

        if response.status_code >= 400:
            # Частые причины: у номера нет WhatsApp, шаблон не одобрен,
            # протух токен. Каскаду это всё равно — он просто уйдёт в SMS.
            detail = response.text[:300]
            logger.warning(
                "Meta WhatsApp rejected",
                extra={"status": response.status_code, "phone": to, "provider_message": detail},
            )
            raise SmsBackendError(
                "Meta WhatsApp не принял сообщение",
                status_code=response.status_code,
                provider_message=detail,
            )

        try:
            data = response.json()
        except ValueError:
            data = {}
        messages = data.get("messages") or [{}]
        return {
            "message_id": messages[0].get("id") or message_id,
            "provider": self.provider,
        }
