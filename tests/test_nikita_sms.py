import xml.etree.ElementTree as ET

import pytest
from django.test import override_settings

from users.sms.exceptions import SmsBackendError
from users.sms.nikita import (
    NikitaSmsBackend,
    assert_allowed_nikita_phone,
    build_message_xml,
    build_nikita_error_message,
    build_otp_text,
    normalize_phone_for_nikita,
    parse_send_response,
)


def test_normalize_phone_for_nikita():
    assert normalize_phone_for_nikita("+996700123456") == "996700123456"
    assert normalize_phone_for_nikita("996700123456") == "996700123456"
    assert normalize_phone_for_nikita("700123456") == "996700123456"


def test_build_message_xml_contains_required_fields():
    xml = build_message_xml(
        login="partner",
        password="secret",
        message_id="ABC123",
        sender="315CARGO",
        text="315CARGO: код 123456",
        phone="996700123456",
        test_mode=True,
    )
    root = ET.fromstring(xml)
    assert root.findtext("login") == "partner"
    assert root.findtext("pwd") == "secret"
    assert root.findtext("id") == "ABC123"
    assert root.findtext("sender") == "315CARGO"
    assert root.findtext("text") == "315CARGO: код 123456"
    assert root.find("phones/phone").text == "996700123456"
    assert root.findtext("test") == "1"


def test_parse_send_response_success():
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<response>
<id>ABC123</id>
<status>0</status>
<phones>1</phones>
<smscnt>1</smscnt>
<message></message>
</response>"""
    parsed = parse_send_response(xml)
    assert parsed["status"] == 0
    assert parsed["id"] == "ABC123"


def test_parse_send_response_with_namespace():
    xml = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<response xmlns="http://Giper.mobi/schema/Message">
<id>TEST12345678</id>
<status>2</status>
<phones>1</phones>
<smscnt>1</smscnt>
</response>"""
    parsed = parse_send_response(xml)
    assert parsed["status"] == 2
    assert parsed["id"] == "TEST12345678"


@override_settings(
    NIKITA_SMS_LOGIN="login",
    NIKITA_SMS_PASSWORD="pwd",
    NIKITA_SMS_SENDER="315CARGO",
    NIKITA_SMS_TEST=False,
    NIKITA_SMS_ALLOWED_PHONE="",
)
def test_nikita_send_otp_success(monkeypatch):
    class FakeResponse:
        content = b"""<?xml version="1.0"?><response><id>MSG1</id><status>0</status><phones>1</phones><smscnt>1</smscnt></response>"""

        @staticmethod
        def raise_for_status():
            return None

    monkeypatch.setattr(
        "users.sms.nikita.requests.post",
        lambda *args, **kwargs: FakeResponse(),
    )
    backend = NikitaSmsBackend()
    result = backend.send_otp("+996700123456", "123456", "login", "MSG1")
    assert result["provider"] == "nikita"
    assert result["message_id"] == "MSG1"


@override_settings(
    NIKITA_SMS_LOGIN="login",
    NIKITA_SMS_PASSWORD="pwd",
    NIKITA_SMS_SENDER="315CARGO",
    NIKITA_SMS_ALLOWED_PHONE="",
)
def test_nikita_send_otp_auth_error(monkeypatch):
    class FakeResponse:
        content = b"""<?xml version="1.0"?><response><status>2</status><message>bad auth</message></response>"""

        @staticmethod
        def raise_for_status():
            return None

    monkeypatch.setattr(
        "users.sms.nikita.requests.post",
        lambda *args, **kwargs: FakeResponse(),
    )
    backend = NikitaSmsBackend()
    with pytest.raises(SmsBackendError) as exc:
        backend.send_otp("+996700123456", "123456", "login", "MSG2")
    assert exc.value.status_code == 2


def test_assert_allowed_nikita_phone_blocks_other_numbers(settings):
    settings.NIKITA_SMS_ALLOWED_PHONE = "+996700111222"
    with pytest.raises(SmsBackendError) as exc:
        assert_allowed_nikita_phone("+996700999888")
    assert exc.value.status_code == 7


@override_settings(NIKITA_SMS_ALLOWED_PHONE="+996700111222")
def test_assert_allowed_nikita_phone_allows_profile_number():
    assert assert_allowed_nikita_phone("996700111222") == "996700111222"


def test_build_nikita_error_message_status_4():
    msg = build_nikita_error_message(4, test_mode=False)
    assert "Недостаточно средств" in msg
    assert "NIKITA_SMS_TEST" in msg
    assert "NIKITA_SMS_ALLOWED_PHONE" in msg


@override_settings(NIKITA_SMS_BRAND="315CARGO")
def test_build_otp_text():
    assert "123456" in build_otp_text("123456")
    assert "315CARGO" in build_otp_text("123456")
