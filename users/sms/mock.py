import logging

logger = logging.getLogger(__name__)


class MockSmsBackend:
    def send_otp(self, phone, code, purpose, message_id):
        logger.info(
            "Mock SMS OTP",
            extra={
                "phone": phone,
                "purpose": purpose,
                "code": code,
                "message_id": message_id,
            },
        )
        return {"message_id": message_id, "provider": "mock"}
