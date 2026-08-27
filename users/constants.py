OTP_CODE_LENGTH = 4

# Wrong-code attempts allowed before an OTP is burned and a new one is required.
# Caps brute-force of the small 4-digit space to MAX_OTP_ATTEMPTS guesses.
MAX_OTP_ATTEMPTS = 5

# Срок жизни OTP. Одно место на всех: и модель, и текст сообщения клиенту —
# иначе при изменении срока сообщение начнёт врать.
OTP_TTL_MINUTES = 5
