"""Клиент smspro.nikita.kg (XML POST /api/message)."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

import requests
from django.conf import settings

from .exceptions import SmsBackendError

logger = logging.getLogger(__name__)

NIKITA_SEND_STATUS = {
    0: "Сообщение принято к отправке",
    1: "Ошибка в формате запроса",
    2: "Неверная авторизация",
    3: "Недопустимый IP-адрес отправителя",
    4: "Недостаточно средств на счёте",
    5: "Недопустимое имя отправителя",
    6: "Сообщение заблокировано по стоп-словам",
    7: "Некорректный номер телефона",
    8: "Неверный формат времени отправки",
    9: "Превышение времени обработки запроса, повторите через 5–10 сек",
    10: "Повтор id сообщения",
    11: "Тестовый режим: сообщение не отправлено и не тарифицируется",
}

PHONE_DIGITS_RE = re.compile(r"\D")


def _xml_local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if tag else tag


def _xml_text_by_local_name(root: ET.Element, local_name: str) -> str:
    for elem in root.iter():
        if _xml_local_tag(elem.tag) == local_name:
            return elem.text or ""
    return ""


def normalize_phone_for_nikita(phone: str) -> str:
    digits = PHONE_DIGITS_RE.sub("", phone or "")
    if digits.startswith("996") and len(digits) == 12:
        return digits
    if len(digits) == 9:
        return f"996{digits}"
    return digits


def phones_match(phone_a: str, phone_b: str) -> bool:
    return normalize_phone_for_nikita(phone_a) == normalize_phone_for_nikita(phone_b)


def build_nikita_error_message(status: int, *, test_mode: bool = False) -> str:
    base = NIKITA_SEND_STATUS.get(status, "Неизвестная ошибка SMS")
    hints: list[str] = []

    if status == 4:
        hints.append("Пополните баланс в кабинете smspro.nikita.kg.")
        if not test_mode:
            hints.append(
                "Либо включите NIKITA_SMS_TEST=1 в .env — запрос уйдёт с флагом test=1 "
                "и не будет списывать средства (ответ Nikita: status 11)."
            )
        hints.append(
            "На тестовом аккаунте Nikita по API можно отправлять только на номер "
            "из профиля. Укажите его в NIKITA_SMS_ALLOWED_PHONE."
        )
    elif status == 3:
        hints.append("Добавьте IP сервера в whitelist в кабинете Nikita.")
    elif status == 5:
        hints.append(
            f"Имя отправителя должно быть одобрено администратором Nikita "
            f"(NIKITA_SMS_SENDER={getattr(settings, 'NIKITA_SMS_SENDER', '')})."
        )
    elif status == 7:
        hints.append(
            "На тестовом аккаунте разрешён только номер из профиля Nikita "
            "(NIKITA_SMS_ALLOWED_PHONE)."
        )

    if hints:
        return f"{base}. {' '.join(hints)}"
    return base


def assert_allowed_nikita_phone(phone: str) -> str:
    normalized_phone = normalize_phone_for_nikita(phone)
    allowed_phone = getattr(settings, "NIKITA_SMS_ALLOWED_PHONE", "") or ""
    if not allowed_phone:
        return normalized_phone

    if not phones_match(normalized_phone, allowed_phone):
        allowed_norm = normalize_phone_for_nikita(allowed_phone)
        raise SmsBackendError(
            "На тестовом аккаунте Nikita по API можно отправлять SMS только на номер "
            f"из профиля: +{allowed_norm}. "
            f"Вы указали: +{normalized_phone}. "
            "Для других номеров на локалке используйте SMS_BACKEND=mock.",
            status_code=7,
        )
    return normalized_phone


def build_otp_text(code: str) -> str:
    brand = getattr(settings, "NIKITA_SMS_BRAND", "315CARGO")
    return f"{brand}: код подтверждения {code}. Действителен 5 мин."


def build_message_xml(
    *,
    login: str,
    password: str,
    message_id: str,
    sender: str,
    text: str,
    phone: str,
    test_mode: bool = False,
) -> bytes:
    root = ET.Element("message")
    ET.SubElement(root, "login").text = login
    ET.SubElement(root, "pwd").text = password
    ET.SubElement(root, "id").text = message_id[:12]
    ET.SubElement(root, "sender").text = sender
    ET.SubElement(root, "text").text = text
    phones = ET.SubElement(root, "phones")
    ET.SubElement(phones, "phone").text = phone
    if test_mode:
        ET.SubElement(root, "test").text = "1"
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def parse_send_response(content: bytes) -> dict:
    root = ET.fromstring(content)
    status_raw = _xml_text_by_local_name(root, "status")
    try:
        status = int(status_raw)
    except (TypeError, ValueError):
        status = -1
    return {
        "id": _xml_text_by_local_name(root, "id"),
        "status": status,
        "phones": _xml_text_by_local_name(root, "phones"),
        "smscnt": _xml_text_by_local_name(root, "smscnt"),
        "message": _xml_text_by_local_name(root, "message"),
    }


class NikitaSmsBackend:
    def __init__(
        self,
        login=None,
        password=None,
        sender=None,
        api_url=None,
        test_mode=None,
        timeout=None,
    ):
        self.login = login or settings.NIKITA_SMS_LOGIN
        self.password = password or settings.NIKITA_SMS_PASSWORD
        self.sender = sender or settings.NIKITA_SMS_SENDER
        self.api_url = api_url or settings.NIKITA_SMS_API_URL
        self.test_mode = (
            settings.NIKITA_SMS_TEST if test_mode is None else test_mode
        )
        self.timeout = timeout or settings.NIKITA_SMS_TIMEOUT

    def send_otp(self, phone, code, purpose, message_id):
        if not self.login or not self.password:
            raise SmsBackendError("Не заданы NIKITA_SMS_LOGIN / NIKITA_SMS_PASSWORD")

        normalized_phone = assert_allowed_nikita_phone(phone)
        if len(normalized_phone) != 12 or not normalized_phone.startswith("996"):
            raise SmsBackendError(
                "Некорректный номер телефона для отправения SMS",
                status_code=7,
            )

        payload = build_message_xml(
            login=self.login,
            password=self.password,
            message_id=message_id,
            sender=self.sender,
            text=build_otp_text(code),
            phone=normalized_phone,
            test_mode=self.test_mode,
        )

        try:
            response = requests.post(
                self.api_url,
                data=payload,
                headers={"Content-Type": "application/xml; charset=UTF-8"},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.exception("Nikita SMS HTTP error")
            raise SmsBackendError("Ошибка связи с SMS-провайдером") from exc

        parsed = parse_send_response(response.content)
        status = parsed["status"]
        if status not in (0, 11):
            description = build_nikita_error_message(status, test_mode=self.test_mode)
            provider_message = parsed.get("message") or ""
            logger.error(
                "Nikita SMS rejected",
                extra={
                    "status": status,
                    "message_id": message_id,
                    "provider_message": provider_message,
                    "sender": self.sender,
                    "phone": normalized_phone,
                },
            )
            raise SmsBackendError(
                description,
                status_code=status,
                provider_message=provider_message,
            )

        logger.info(
            "Nikita SMS accepted",
            extra={
                "message_id": parsed["id"] or message_id,
                "phone": normalized_phone,
                "purpose": purpose,
                "test_mode": self.test_mode,
                "status": status,
            },
        )
        return {
            "message_id": parsed["id"] or message_id,
            "provider": "nikita",
            "test_mode": self.test_mode or status == 11,
            "smscnt": parsed.get("smscnt"),
        }
