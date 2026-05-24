class SmsBackendError(Exception):
    """Ошибка отправки SMS через провайдера."""

    def __init__(self, message, *, status_code=None, provider_message=""):
        super().__init__(message)
        self.status_code = status_code
        self.provider_message = provider_message
