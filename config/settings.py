from datetime import timedelta
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


SECRET_KEY = os.getenv("SECRET_KEY", "unsafe-dev-key")
DEBUG = env_bool("DEBUG", True)
ENABLE_API_DOCS = env_bool("ENABLE_API_DOCS", True)

ALLOWED_HOSTS = [host.strip() for host in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if host.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular",
    "corsheaders",
    "common.apps.CommonConfig",
    "cargo.apps.CargoConfig",
    "pickup_points.apps.PickupPointsConfig",
    "users.apps.UsersConfig",
    "shops.apps.ShopsConfig",
    "orders.apps.OrdersConfig",
    "parcels.apps.ParcelsConfig",
    "city_delivery.apps.CityDeliveryConfig",
    "notifications.apps.NotificationsConfig",
    "integrations.apps.IntegrationsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
        conn_max_age=600,
    )
}

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Asia/Bishkek"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# --- Ссылки-приглашения карго ---------------------------------------------
# Клиент переходит по https://<база>/j/<slug> → открывается приложение с уже
# выбранным карго. Домен вынесен в env: он же прописан в .well-known-файлах
# и в конфиге мобильного приложения — менять их надо синхронно.
INVITE_LINK_BASE_URL = os.getenv("INVITE_LINK_BASE_URL", "https://315cargo.com").rstrip("/")
# Своя схема приложения — работает без верификации домена (запасной путь).
MOBILE_APP_SCHEME = os.getenv("MOBILE_APP_SCHEME", "cargo315")
ANDROID_PACKAGE_NAME = os.getenv("ANDROID_PACKAGE_NAME", "com.cargo315.app")
# Пусто → кнопка магазина не показывается (iOS-приложение ещё не опубликовано).
APP_STORE_URL = os.getenv("APP_STORE_URL", "")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CORS: React-панель (по умолчанию dev-порт Vite). Прод-origin добавь через env.
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
    ).split(",")
    if origin.strip()
]
# JWT в заголовке Authorization — cookies не нужны.
CORS_ALLOW_CREDENTIALS = False

# Прод-хардненинг: включается только когда DEBUG=0 (локально не влияет).
if not DEBUG:
    # За обратным прокси (nginx) определяем HTTPS по заголовку.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"


def _parse_otp_test_numbers(raw):
    """`+996700000000:0000,+996...:1234` → {phone: fixed_code}."""
    result = {}
    for pair in (raw or "").split(","):
        pair = pair.strip()
        if ":" in pair:
            phone, code = pair.split(":", 1)
            if phone.strip() and code.strip():
                result[phone.strip()] = code.strip()
    return result


# Тестовые номера для ревьюеров магазинов: фиксированный код, без реальной SMS,
# без истечения/лимита попыток. Требует существующего пользователя с этим phone.
OTP_TEST_NUMBERS = _parse_otp_test_numbers(
    os.getenv("OTP_TEST_NUMBERS", "+996700000000:0000")
)

# Резервный мастер-код: если задан (не пусто), проходит верификацию для ЛЮБОГО
# номера и делает регистрацию/вход устойчивыми к сбою SMS-провайдера (Nikita):
# send-code не блокирует поток, клиент вводит этот код. Меняется через .env без
# деплоя. ВНИМАНИЕ: это бэкдор — держите код в секрете.
OTP_MASTER_CODE = os.getenv("OTP_MASTER_CODE", "").strip()

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_RATES": {
        "sms": "3/min",
        "auth": "10/min",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.getenv("JWT_ACCESS_LIFETIME_MINUTES", "60"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.getenv("JWT_REFRESH_LIFETIME_DAYS", "30"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "315CARGO API",
    "DESCRIPTION": (
        "REST API мобильного приложения карго-сервиса.\n\n"
        "**Авторизация:** получите `access` через `POST /api/auth/verify-code/`, "
        "нажмите **Authorize** и введите `Bearer <access>`.\n\n"
        "Публичные endpoint'ы: `send-code`, `verify-code`, `refresh`."
    ),
    "VERSION": "1.0.0",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/",
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": False,
        "filter": True,
        "tryItOutEnabled": True,
    },
    "TAGS": [
        {"name": "cargo", "description": "Карго-центры платформы"},
        {"name": "auth", "description": "SMS-авторизация, JWT refresh/logout"},
        {"name": "profile", "description": "Профиль клиента, QR, настройки уведомлений"},
        {"name": "pickup-points", "description": "ПВЗ"},
        {"name": "shops", "description": "Китайские маркетплейсы"},
        {"name": "orders", "description": "Заказы клиента"},
        {"name": "parcels", "description": "Посылки и история статусов"},
        {"name": "city-delivery", "description": "Доставка по городу"},
        {"name": "notifications", "description": "Push и in-app уведомления"},
        {"name": "integrations", "description": "Pinduoduo и внешние интеграции"},
    ],
}

SMS_BACKEND = os.getenv("SMS_BACKEND", "auto")  # auto | mock | nikita
# Каналы доставки OTP по порядку. Первый доставивший останавливает перебор,
# поэтому дешёвый WhatsApp стоит перед SMS. Убрать WhatsApp — убрать из списка.
OTP_CHANNELS = os.getenv("OTP_CHANNELS", "sms")  # напр. "whatsapp,sms"

# Self-hosted шлюз WhatsApp (WAHA). Держит сессию обычного аккаунта и отдаёт
# REST API; слушает только localhost, наружу не публикуется.
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL", "")
WHATSAPP_API_KEY = os.getenv("WHATSAPP_API_KEY", "")
WHATSAPP_SESSION = os.getenv("WHATSAPP_SESSION", "default")
# Имя отправителя в тексте кода. Своё, не SMS-овское: см. build_otp_text.
WHATSAPP_BRAND = os.getenv("WHATSAPP_BRAND", "315CARGO")

# Провайдер канала "whatsapp": waha (self-hosted) | meta (Cloud API).
WHATSAPP_PROVIDER = os.getenv("WHATSAPP_PROVIDER", "waha")

# --- WhatsApp Cloud API (Meta) ---
# Текст сообщения задаёт Meta, мы передаём только код: см. meta_whatsapp.py.
META_WA_PHONE_NUMBER_ID = os.getenv("META_WA_PHONE_NUMBER_ID", "")
META_WA_TOKEN = os.getenv("META_WA_TOKEN", "")
META_WA_TEMPLATE = os.getenv("META_WA_TEMPLATE", "otp_code")
META_WA_LANG = os.getenv("META_WA_LANG", "ru")
META_WA_API_VERSION = os.getenv("META_WA_API_VERSION", "v21.0")
# Тип кнопки в одобренном шаблоне: url (one-tap) | copy_code. Перепутать
# нельзя — Meta отклонит отправку с #132018.
META_WA_OTP_BUTTON = os.getenv("META_WA_OTP_BUTTON", "url")
META_WA_TIMEOUT = int(os.getenv("META_WA_TIMEOUT", "15"))
WHATSAPP_TIMEOUT = int(os.getenv("WHATSAPP_TIMEOUT", "15"))

NIKITA_SMS_LOGIN = os.getenv("NIKITA_SMS_LOGIN", os.getenv("SMS_PROVIDER_LOGIN", ""))
NIKITA_SMS_PASSWORD = os.getenv("NIKITA_SMS_PASSWORD", os.getenv("SMS_PROVIDER_PASSWORD", ""))
NIKITA_SMS_SENDER = os.getenv("NIKITA_SMS_SENDER", os.getenv("SMS_PROVIDER_SENDER", "315CARGO"))
NIKITA_SMS_API_URL = os.getenv(
    "NIKITA_SMS_API_URL", "https://smspro.nikita.kg/api/message"
)
NIKITA_SMS_TEST = env_bool("NIKITA_SMS_TEST", False)
NIKITA_SMS_TIMEOUT = int(os.getenv("NIKITA_SMS_TIMEOUT", "30"))
NIKITA_SMS_BRAND = os.getenv("NIKITA_SMS_BRAND", "315CARGO")
# На тестовом аккаунте Nikita API принимает только номер из профиля кабинета.
NIKITA_SMS_ALLOWED_PHONE = os.getenv("NIKITA_SMS_ALLOWED_PHONE", "")
FCM_CREDENTIALS_PATH = os.getenv("FCM_CREDENTIALS_PATH", "")

# dotted path to PinduoduoClient implementation,
# e.g. "integrations.pinduoduo.clients.WebViewClient".
# Leave empty to use the no-op NullPinduoduoClient.
PINDUODUO_CLIENT_PATH = os.getenv("PINDUODUO_CLIENT_PATH", "")
TAOBAO_CLIENT_PATH = os.getenv("TAOBAO_CLIENT_PATH", "")
SHOP_1688_CLIENT_PATH = os.getenv("SHOP_1688_CLIENT_PATH", "")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL

# Авто-цепочка статусов после 1-го скана (склад в Китае). Значения — сколько
# времени посылка остаётся в статусе, прежде чем перейти в следующий (секунды).
# Celery-задача `parcels.advance_parcels` (beat, каждые 5 мин) двигает посылки
# по цепочке. Локально без Celery: `manage.py advance_parcels --loop`. После
# "arrived_kyrgyzstan" — ожидание 2-го скана в ПВЗ (at_pickup_point).
# Маршрут: Китай → (10с) обработка → (4д) Топа → (2д) в пути → (2д) Кыргызстан.
# Ключ = текущий статус, значение = задержка перед переходом к следующему.
# Сколько статус держится, прежде чем посылка уйдёт на следующий. Ключ —
# текущий статус, значение — задержка перед переходом. Порядок переходов
# задаёт AUTO_FLOW; отсчёт накопительный от скана на складе в Китае.
#
#   скан в Китае → +10 сек  → Классификация и обработка
#                → +1 день  → В пути
#                → +4 дня   → Прибыл в Топа
#                → +4 дня   → Прибыл в Кыргызстан   (2 дня стоянка + 2 в пути)
#   → скан в ПВЗ (вручную)  → Прибыл в ПВЗ
#
# Итого до Кыргызстана ~9 дней. Меняется через .env без деплоя, но требует
# рестарта cargo-celery.
AUTO_STATUS_DELAYS = {
    "arrived_china_warehouse": int(os.getenv("AUTO_DELAY_ARRIVED_CHINA", 10)),
    "processing": int(os.getenv("AUTO_DELAY_PROCESSING", 1 * 86400)),
    "in_transit": int(os.getenv("AUTO_DELAY_IN_TRANSIT", 4 * 86400)),
    "arrived_topa": int(os.getenv("AUTO_DELAY_TOPA", 4 * 86400)),
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}
