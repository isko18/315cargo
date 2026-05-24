import logging
import random
import re
import secrets
import string
from datetime import timedelta
from io import BytesIO

import qrcode
from django.core.files.base import ContentFile
from django.utils import timezone
from rest_framework.exceptions import Throttled, ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from .constants import OTP_CODE_LENGTH
from .models import SMSCode, User
from .sms import get_sms_backend
from .sms.exceptions import SmsBackendError

logger = logging.getLogger(__name__)

PHONE_RE = re.compile(r"^\+?\d{10,15}$")


def validate_phone(phone):
    if not PHONE_RE.match(phone or ""):
        raise ValidationError("Invalid phone number")
    return phone


def generate_client_code(cargo):
    while True:
        code = "C" + "".join(random.choices(string.digits, k=7))
        if not User.objects.filter(cargo=cargo, client_code=code).exists():
            return code


def generate_qr_code(user):
    if not user.client_code:
        return None
    image = qrcode.make(user.client_code)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    filename = f"{user.client_code}.png"
    user.qr_code_image.save(filename, ContentFile(buffer.getvalue()), save=False)
    return user.qr_code_image


def issue_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def _generate_sms_message_id():
    return secrets.token_hex(6).upper()[:12]


def send_sms_code(phone, purpose=SMSCode.Purpose.LOGIN):
    phone = validate_phone(phone)
    recent_code = SMSCode.objects.filter(
        phone=phone,
        purpose=purpose,
        created_at__gte=timezone.now() - timedelta(seconds=60),
    ).first()
    if recent_code:
        raise Throttled(detail="SMS code was sent recently")

    code = "".join(random.choices(string.digits, k=OTP_CODE_LENGTH))
    message_id = _generate_sms_message_id()
    backend = get_sms_backend()

    try:
        result = backend.send_otp(phone, code, purpose, message_id)
    except SmsBackendError as exc:
        logger.error(
            "SMS delivery failed",
            extra={
                "phone": phone,
                "purpose": purpose,
                "status_code": exc.status_code,
                "provider_message": exc.provider_message,
            },
        )
        error_detail = {"detail": str(exc)}
        if exc.status_code is not None:
            error_detail["sms_status"] = exc.status_code
        if exc.provider_message:
            error_detail["sms_provider_message"] = exc.provider_message
        raise ValidationError(error_detail) from exc

    sms_code = SMSCode.objects.create(
        phone=phone,
        code=code,
        purpose=purpose,
        expires_at=SMSCode.default_expires_at(),
        provider_message_id=result.get("message_id", message_id),
    )
    logger.info(
        "SMS OTP sent",
        extra={
            "phone": phone,
            "purpose": purpose,
            "provider": result.get("provider"),
            "message_id": sms_code.provider_message_id,
        },
    )
    return sms_code


def verify_sms_code(phone, code):
    phone = validate_phone(phone)
    sms_code = SMSCode.objects.filter(phone=phone, code=code, is_used=False).first()
    if not sms_code or sms_code.is_expired:
        raise ValidationError("Invalid or expired SMS code")
    sms_code.is_used = True
    sms_code.save(update_fields=("is_used",))
    logger.info("SMS code verified", extra={"phone": phone})
    return sms_code
