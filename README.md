# 315CARGO Backend

Django + Django REST Framework backend для мобильного приложения карго-сервиса.

## Стек

- Python 3.12+
- Django 5+ / DRF
- PostgreSQL
- SimpleJWT (access + refresh + blacklist)
- django-filter, drf-spectacular (Swagger)
- Celery + Redis (периодическая синхронизация Pinduoduo)
- firebase-admin (push FCM, mock-fallback)
- qrcode + Pillow (генерация персональных QR клиентов)

## Установка

```bash
python -m venv venv
.\venv\Scripts\activate          # Windows
# source venv/bin/activate       # Linux/macOS
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
copy .env.example .env
```

Заполните `.env` (см. ниже). По умолчанию подходит SQLite, если не задан `DATABASE_URL`.

## Запуск

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo            # демо-данные (ПВЗ, магазины, тарифы, демо-клиент)
python manage.py runserver
```

Swagger при `ENABLE_API_DOCS=True`: <http://127.0.0.1:8000/api/docs/>.

## Тесты

```bash
python -m pytest
```

## Celery

```bash
celery -A config worker -l info
celery -A config beat -l info
```

Beat расписание: `integrations.sync_all_pinduoduo_accounts` каждый час.

## Переменные окружения

| Имя | Описание |
|---|---|
| `SECRET_KEY` | Django secret |
| `DEBUG` | true/false |
| `DATABASE_URL` | postgres://… или sqlite |
| `ALLOWED_HOSTS` | через запятую |
| `ENABLE_API_DOCS` | включает `/api/docs/` |
| `JWT_ACCESS_LIFETIME_MINUTES` | срок жизни access-токена |
| `JWT_REFRESH_LIFETIME_DAYS` | срок жизни refresh-токена |
| `SMS_BACKEND` | `auto` / `mock` / `nikita` |
| `NIKITA_SMS_LOGIN` | логин smspro.nikita.kg |
| `NIKITA_SMS_PASSWORD` | пароль smspro.nikita.kg |
| `NIKITA_SMS_SENDER` | имя отправителя (до 11 лат. символов), должно быть одобрено в кабинете Nikita |
| `NIKITA_SMS_API_URL` | по умолчанию `https://smspro.nikita.kg/api/message` |
| `NIKITA_SMS_TEST` | `1` — тестовый режим без тарификации |
| `NIKITA_SMS_BRAND` | бренд в тексте OTP (по умолчанию `315CARGO`) |
| `FCM_CREDENTIALS_PATH` | путь к Firebase service account JSON (если пусто — mock push) |
| `PINDUODUO_CLIENT_PATH` | dotted-path к реализации `PinduoduoClient` (если пусто — no-op) |
| `REDIS_URL` | для Celery |

## API

### Auth

| Метод | URL | Описание |
|---|---|---|
| POST | `/api/auth/send-code/` | Отправить SMS-код |
| POST | `/api/auth/verify-code/` | Проверить код. Если клиент новый — нужно передать `pickup_point_id` и `full_name`. Возвращает `access`, `refresh`, `user`, `is_new_user`. |
| POST | `/api/auth/refresh/` | Получить новые `access` + `refresh` |
| POST | `/api/auth/logout/` | Blacklist refresh-токена |

### Профиль

- `GET /api/profile/`
- `PATCH /api/profile/` (можно поменять `full_name`, `pickup_point`)
- `GET /api/profile/qr/` — клиентский код и QR
- `GET /api/profile/notification-preferences/`
- `PATCH /api/profile/notification-preferences/`

### Справочники

- `GET /api/pickup-points/`
- `GET /api/shops/` — возвращает `open_url` уже с подставленным `client_code` (для query_param стратегии), `client_code` для clipboard, либо `instruction` для manual.
- `GET /api/city-delivery-tariffs/`

### Заказы и посылки

- `GET /api/orders/?status=&source=&track_number=&date_from=&date_to=`
- `GET /api/orders/{id}/`
- `POST /api/orders/manual/` — ручное создание
- `GET /api/parcels/?status=&track_number=&date_from=&date_to=`
- `GET /api/parcels/{id}/`
- `GET /api/parcels/{id}/history/`

### Доставка по городу

- `POST /api/city-delivery/` — создать заявку. Цена и тариф рассчитываются автоматически по весу посылки и ПВЗ клиента.
- `GET /api/city-delivery/`
- `GET /api/city-delivery/{id}/`
- `POST /api/city-delivery/estimate/` — предварительный расчёт цены

### Уведомления

- `GET /api/notifications/`
- `GET /api/notifications/unread-count/`
- `POST /api/notifications/{id}/read/`
- `POST /api/notifications/read-all/`
- `POST /api/device-tokens/` — регистрация FCM-токена

### Pinduoduo

- `POST /api/integrations/pinduoduo/connect/`
- `POST /api/integrations/pinduoduo/disconnect/`
- `POST /api/integrations/pinduoduo/sync/`
- `GET /api/integrations/pinduoduo/status/`
- `POST /api/integrations/pinduoduo/webhook/` — admin-only, принимает массив заказов от внешнего парсера

## Импорт посылок (CSV)

В админке `/admin/parcels/parcel/` → кнопка «Импорт из CSV». Формат:

```csv
track_number,client_code,status,location,weight,volume,delivery_price
LP123,C1234567,arrived_china_warehouse,Guangzhou,2.5,0.05,1500
```

## Audit log

Все критичные действия (регистрация, вход, выход, импорт посылок, операции с Pinduoduo) пишутся в `common.AuditLog` и доступны через админку. Журнал read-only, удаление только для суперпользователя.

## Архитектурные заметки

### SMS (Nikita smspro.nikita.kg)

OTP отправляется через XML API `POST https://smspro.nikita.kg/api/message`.

- Если заданы `NIKITA_SMS_LOGIN` и `NIKITA_SMS_PASSWORD` — используется Nikita (`SMS_BACKEND=auto` по умолчанию).
- Если credentials пусты — mock (код пишется в лог сервера, удобно для локальной разработки).
- `NIKITA_SMS_TEST=1` — запрос обрабатывается шлюзом, но SMS не отправляется и не тарифицируется (статус 11).
- Имя отправителя (`NIKITA_SMS_SENDER`) должно быть зарегистрировано и одобрено в личном кабинете Nikita.
- IP сервера должен быть разрешён в кабинете Nikita (иначе статус 3).

Текст OTP: `315CARGO: код подтверждения 123456. Действителен 5 мин.`

Реализация: `users/sms/nikita.py`, точка входа — `users.services.send_sms_code`.

### Push
`notifications.services.send_push_notification` использует `firebase-admin`, если задан `FCM_CREDENTIALS_PATH`. Без него — mock. Неактивные токены автоматически помечаются `is_active=False` после ошибки доставки.

### Pinduoduo (высокорисковый модуль, ТЗ п.13.1)
Слой сделан расширяемым:

1. **Null-клиент** (по умолчанию) — не делает запросов.
2. **Custom-клиент** — реализуйте `PinduoduoClient.fetch_orders(session_data) -> Iterable[dict]` и пропишите путь в `PINDUODUO_CLIENT_PATH`.
3. **Webhook** — внешний воркер (например, headless-парсер на отдельном сервере) шлёт заказы на `/api/integrations/pinduoduo/webhook/`, требует staff-аутентификации.

### Локализация
`LANGUAGE_CODE=ru-ru`, `TIME_ZONE=Asia/Bishkek`. Все `verbose_name` и `choices` обёрнуты в `gettext_lazy`. Для добавления кыргызского — `python manage.py makemessages -l ky`.

## Что осталось / следующие шаги

- Реализация конкретного `PinduoduoClient` (если планируется WebView-парсер — отдельный микросервис)
- Курьерское приложение / роль курьера
- Мобильный клиент (Flutter / RN)
- CI (pytest + ruff)
