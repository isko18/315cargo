"""Проверка аккаунта Nikita SMS через /api/info."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import requests
from django.conf import settings

from users.sms.nikita import NIKITA_SEND_STATUS, _xml_text_by_local_name


def check_nikita_account() -> dict:
    login = settings.NIKITA_SMS_LOGIN
    password = settings.NIKITA_SMS_PASSWORD
    if not login or not password:
        return {"ok": False, "error": "NIKITA_SMS_LOGIN / NIKITA_SMS_PASSWORD не заданы"}

    root = ET.Element("info")
    ET.SubElement(root, "login").text = login
    ET.SubElement(root, "pwd").text = password
    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    url = settings.NIKITA_SMS_API_URL.replace("/api/message", "/api/info")
    try:
        response = requests.post(
            url,
            data=payload,
            headers={"Content-Type": "application/xml; charset=UTF-8"},
            timeout=settings.NIKITA_SMS_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return {"ok": False, "error": f"HTTP ошибка: {exc}"}

    parsed_root = ET.fromstring(response.content)
    status_raw = _xml_text_by_local_name(parsed_root, "status")
    try:
        status = int(status_raw)
    except (TypeError, ValueError):
        status = -1

    info_status = {
        0: "OK",
        1: "Ошибка формата",
        2: "Неверная авторизация",
        3: "IP не разрешён",
    }

    result = {
        "ok": status == 0,
        "status": status,
        "status_text": info_status.get(status, "Неизвестно"),
        "account": _xml_text_by_local_name(parsed_root, "account"),
        "smsprice": _xml_text_by_local_name(parsed_root, "smsprice"),
        "state": _xml_text_by_local_name(parsed_root, "state"),
        "sender": settings.NIKITA_SMS_SENDER,
        "test_mode": settings.NIKITA_SMS_TEST,
    }
    if status != 0:
        result["error"] = info_status.get(status, NIKITA_SEND_STATUS.get(status, "Ошибка"))
    return result
