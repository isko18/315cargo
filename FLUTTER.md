# 315CARGO — документация для Flutter-клиента

Полное руководство по разработке мобильного приложения на Flutter для backend 315CARGO (Django REST Framework + JWT).

**Актуально на 2026-08-06.** Краткий список того, что поменялось в API за последние
релизы (с примерами и чеклистом для мобилки) — в [MOBILE_UPDATES.md](MOBILE_UPDATES.md).
Ломающие изменения этой версии:

| Что | Было | Стало |
|---|---|---|
| Валюта | доллар | **сом (KGS)** во всех суммах, включая `delivery_price` |
| Тариф карго | `price_per_kg_usd` | **`price_per_kg_kgs`** |
| Код клиента | `C` + 7 случайных цифр | **префикс карго + 4 цифры** (`X0001`), формат задаёт карго |
| Статусы посылки | 11 значений | **+4**: `in_storage`, `in_transit`, `processing`, `arrived_topa` |
| Адрес для PDD | не было | `GET /api/delivery-address/` — новый раздел в справочнике API |
| Индекс в адресе | `postal_code` в ответе и в строке | **удалён совсем** — используйте `detail_address_full` |

---

## Содержание

1. [Обзор](#1-обзор)
2. [Требования и окружение](#2-требования-и-окружение)
3. [Создание проекта](#3-создание-проекта)
4. [Конфигурация API](#4-конфигурация-api)
5. [Архитектура приложения](#5-архитектура-приложения)
6. [Аутентификация (SMS + JWT)](#6-аутентификация-sms--jwt)
7. [HTTP-слой (Dio)](#7-http-слой-dio)
8. [Модели данных (Dart)](#8-модели-данных-dart)
9. [Справочник API](#9-справочник-api)
10. [Экраны и навигация](#10-экраны-и-навигация)
11. [Push-уведомления (FCM)](#11-push-уведомления-fcm)
12. [Работа с магазинами (WebView / clipboard)](#12-работа-с-магазинами-webview--clipboard)
13. [Интеграция Pinduoduo](#13-интеграция-pinduoduo)
14. [Обработка ошибок](#14-обработка-ошибок)
15. [Локализация и форматы](#15-локализация-и-форматы)
16. [Тестирование](#16-тестирование)
17. [Сборка и публикация](#17-сборка-и-публикация)
18. [Чеклист перед релизом](#18-чеклист-перед-релизом)

---

## 1. Обзор

315CARGO — мобильное приложение карго-сервиса для клиентов из Кыргызстана. Backend предоставляет REST API для:

- SMS-регистрации и входа (мультитенантность по карго-центрам)
- Профиля клиента с персональным кодом и QR
- Отслеживания заказов и посылок
- Адреса склада в Китае для заказов на маркетплейсах (готовая строка для 智能填写)
- Доставки по городу
- Каталога китайских маркетплейсов
- In-app и push-уведомлений
- Интеграции с Pinduoduo

**Swagger (при `ENABLE_API_DOCS=True`):**

| URL | Описание |
|---|---|
| `/api/docs/` | Swagger UI |
| `/api/redoc/` | ReDoc |
| `/api/schema/` | OpenAPI JSON |

**Базовый URL API:** `https://<your-domain>/api/`

**Часовой пояс сервера:** `Asia/Bishkek`  
**Язык API:** русский (`ru-ru`)

---

## 2. Требования и окружение

| Компонент | Версия |
|---|---|
| Flutter SDK | ≥ 3.16 |
| Dart | ≥ 3.2 |
| Android | minSdk 21+, targetSdk 34+ |
| iOS | 13.0+ |
| Firebase | для push (FCM) |

### Рекомендуемые пакеты

```yaml
dependencies:
  flutter:
    sdk: flutter

  # HTTP
  dio: ^5.4.0
  pretty_dio_logger: ^1.3.1        # только debug

  # Хранение токенов
  flutter_secure_storage: ^9.0.0

  # Состояние (на выбор)
  flutter_riverpod: ^2.5.0
  # или provider / bloc

  # Навигация
  go_router: ^14.0.0

  # JSON
  json_annotation: ^4.9.0
  freezed_annotation: ^2.4.0       # опционально

  # UI
  cached_network_image: ^3.3.0
  qr_flutter: ^4.1.0               # отображение QR локально
  webview_flutter: ^4.7.0
  url_launcher: ^6.2.0

  # Push
  firebase_core: ^3.0.0
  firebase_messaging: ^15.0.0

  # Прочее
  intl: ^0.19.0
  connectivity_plus: ^6.0.0

dev_dependencies:
  build_runner: ^2.4.0
  json_serializable: ^6.8.0
  freezed: ^2.5.0
  flutter_test:
    sdk: flutter
  mocktail: ^1.0.0
```

---

## 3. Создание проекта

```bash
flutter create --org kg.cargo315 cargo315_app
cd cargo315_app
flutter pub get
```

### Flavors / окружения

Создайте три конфигурации:

| Flavor | Base URL | Назначение |
|---|---|---|
| `dev` | `http://10.0.2.2:8000/api/` (Android emulator) | локальная разработка |
| `staging` | `https://staging.315cargo.kg/api/` | тестовый сервер |
| `prod` | `https://api.315cargo.kg/api/` | продакшен |

```dart
// lib/core/config/app_config.dart
enum Environment { dev, staging, prod }

class AppConfig {
  const AppConfig({
    required this.baseUrl,
    required this.environment,
  });

  final String baseUrl;
  final Environment environment;

  static AppConfig of(Environment env) => switch (env) {
        Environment.dev => const AppConfig(
            baseUrl: 'http://10.0.2.2:8000/api/',
            environment: Environment.dev,
          ),
        Environment.staging => const AppConfig(
            baseUrl: 'https://staging.315cargo.kg/api/',
            environment: Environment.staging,
          ),
        Environment.prod => const AppConfig(
            baseUrl: 'https://api.315cargo.kg/api/',
            environment: Environment.prod,
          ),
      };
}
```

> **iOS Simulator / физическое устройство:** замените `10.0.2.2` на IP вашего компьютера в локальной сети.

---

## 4. Конфигурация API

### Заголовки по умолчанию

```dart
final headers = {
  'Content-Type': 'application/json',
  'Accept': 'application/json',
  'Accept-Language': 'ru',
};
```

### Авторизация

Все защищённые endpoint'ы требуют заголовок:

```
Authorization: Bearer <access_token>
```

Публичные endpoint'ы (без токена):

- `GET /api/cargo-companies/`
- `GET /api/pickup-points/?cargo=<id>`
- `POST /api/auth/send-code/`
- `POST /api/auth/verify-code/`
- `POST /api/auth/refresh/`

### JWT-параметры (сервер)

| Параметр | По умолчанию |
|---|---|
| Access token | 60 минут |
| Refresh token | 30 дней |
| Ротация refresh | включена (при refresh выдаётся новая пара) |
| Blacklist | включена (logout инвалидирует refresh) |

### Rate limiting

| Scope | Лимит | Endpoint'ы |
|---|---|---|
| `sms` | 3 запроса/мин | `send-code` |
| `auth` | 10 запросов/мин | `verify-code`, `refresh` |

При превышении: HTTP **429**, тело `{"detail": "..."}`.

### Пагинация

API **не использует пагинацию** — списки возвращаются целиком. На клиенте реализуйте локальную фильтрацию и lazy-loading UI при больших списках.

---

## 5. Архитектура приложения

Рекомендуемая структура каталогов:

```
lib/
├── main.dart
├── app.dart
├── core/
│   ├── config/
│   ├── network/
│   │   ├── api_client.dart
│   │   ├── auth_interceptor.dart
│   │   └── api_exception.dart
│   ├── storage/
│   │   └── token_storage.dart
│   └── utils/
├── features/
│   ├── auth/
│   │   ├── data/
│   │   ├── domain/
│   │   └── presentation/
│   ├── profile/
│   ├── orders/
│   ├── parcels/
│   ├── city_delivery/
│   ├── shops/
│   ├── notifications/
│   └── pinduoduo/
└── shared/
    ├── models/
    ├── widgets/
    └── theme/
```

### Слои

```
Presentation (UI) → Domain (use cases) → Data (repositories → API)
```

---

## 6. Аутентификация (SMS + JWT)

### Мультитенантность

Платформа обслуживает несколько карго-центров, поэтому `cargo_id` обязателен во всех
auth-запросах: SMS-код привязан к карго, для которого он выпущен.

> ⚠️ **Изменено:** раньше один номер мог завести отдельные аккаунты в разных карго.
> Сейчас **клиентский аккаунт — один на номер телефона глобально**. Если клиент с этим
> номером уже существует (в любом карго), `verify-code` выполняет **вход в него**,
> а не создаёт дубль, — при этом карго аккаунта не меняется. Признак в ответе:
> `is_new_user: false`.

Номер нормализуется на сервере к виду `+<цифры>`: `+996 700 00-00-00`, `996700000000`
и `+996700000000` — один и тот же номер. Отправлять можно в любом формате, но хранить
и сравнивать на клиенте — то, что вернул сервер.

### Flow регистрации

```mermaid
sequenceDiagram
    participant U as Пользователь
    participant A as Flutter App
    participant B as Backend

    U->>A: Выбирает карго-центр
    A->>B: GET /api/cargo-companies/
    B-->>A: Список карго + ПВЗ
    U->>A: Выбирает ПВЗ, вводит телефон и ФИО
    A->>B: POST /api/auth/send-code/ (purpose=register)
    B-->>A: 200 OK
    U->>A: Вводит SMS-код (4 цифры)
    A->>B: POST /api/auth/verify-code/
    B-->>A: access, refresh, user, is_new_user=true
    A->>A: Сохраняет токены в SecureStorage
```

### Flow входа

```mermaid
sequenceDiagram
    participant U as Пользователь
    participant A as Flutter App
    participant B as Backend

    U->>A: Выбирает карго + вводит телефон
    A->>B: POST /api/auth/send-code/ (purpose=login)
    Note over B: Проверяет, что пользователь существует
    U->>A: Вводит SMS-код
    A->>B: POST /api/auth/verify-code/
    B-->>A: access, refresh, user, is_new_user=false
```

### Шаг 1. Список карго-центров

```
GET /api/cargo-companies/
```

Ответ (массив):

```json
[
  {
    "id": 1,
    "title": "315CARGO Бишкек",
    "slug": "315cargo-bishkek",
    "code": "x69610",
    "description": "...",
    "logo": "https://api.example.com/media/cargo_logos/logo.png",
    "phone": "+996...",
    "address": "...",
    "price_per_kg_kgs": "306.25",
    "pickup_points": [
      {
        "id": 1,
        "title": "ПВЗ Центральный",
        "address": "...",
        "phone": "+996...",
        "work_schedule": "Пн-Сб 9:00-18:00"
      }
    ]
  }
]
```

Поля карго:

- `code` — **код карго** на складе в Китае (напр. `x69610`), может быть `null`. Клиент указывает его в адресе доставки перед своим кодом (см. «Адрес доставки в Китае»).
- `recipient_name` — ФИО получателя в Китае для этого карго (收货人). Отдельно тянуть не нужно: в `/api/delivery-address/` оно уже подставлено в `recipient` и `one_line`.
- `price_per_kg_kgs` — тариф приёмки, **сом за кг** (раньше поле называлось `price_per_kg_usd` и было в долларах).

### Шаг 2. Отправка SMS

```
POST /api/auth/send-code/
```

Тело:

```json
{
  "phone": "+996700000000",
  "cargo_id": 1,
  "purpose": "register"
}
```

| Поле | Тип | Обязательно | Описание |
|---|---|---|---|
| `phone` | string | да | `+996...`, 10–15 цифр |
| `cargo_id` | int | да | ID карго-центра |
| `purpose` | string | нет | `register` (по умолчанию для новых) или `login` |

**Ответ 200:**

```json
{
  "detail": "SMS code sent"
}
```

При mock-SMS на сервере может быть поле `warning` — покажите его в debug-режиме.

**Ошибки:**

| Код | Причина |
|---|---|
| 400 | Невалидный телефон |
| 400 | `purpose=login`, пользователь не найден в этом карго |
| 429 | Повторная отправка раньше 60 секунд |

### Шаг 3. Проверка кода

```
POST /api/auth/verify-code/
```

**Регистрация:**

```json
{
  "phone": "+996700000000",
  "code": "1234",
  "cargo_id": 1,
  "pickup_point_id": 1,
  "full_name": "Иван Иванов"
}
```

**Вход:**

```json
{
  "phone": "+996700000000",
  "code": "1234",
  "cargo_id": 1
}
```

**Ответ 200:**

```json
{
  "access": "eyJ...",
  "refresh": "eyJ...",
  "is_new_user": true,
  "user": {
    "id": 1,
    "cargo": 1,
    "cargo_title": "315CARGO Бишкек",
    "phone": "+996700000000",
    "full_name": "Иван Иванов",
    "pickup_point": 1,
    "pickup_point_title": "ПВЗ Центральный",
    "client_code": "X0001",
    "qr_code_image": "https://api.example.com/media/qr_codes/X0001.png",
    "is_cargo_admin": false,
    "created_at": "2026-01-01T12:00:00+06:00",
    "updated_at": "2026-01-01T12:00:00+06:00"
  }
}
```

> После регистрации сервер автоматически генерирует `client_code` (формат `C` + 7 цифр) и QR-изображение. При первом входе создаётся welcome-уведомление.

### Шаг 4. Обновление токена

```
POST /api/auth/refresh/
```

```json
{ "refresh": "eyJ..." }
```

**Ответ 200:**

```json
{
  "access": "eyJ...",
  "refresh": "eyJ..."
}
```

> **Важно:** при каждом refresh сервер выдаёт **новую пару** access + refresh. Сохраняйте оба.

### Шаг 5. Выход

```
POST /api/auth/logout/
Authorization: Bearer <access>
```

```json
{ "refresh": "eyJ..." }
```

**Ответ:** `204 No Content`

После logout refresh-токен попадает в blacklist.

### Хранение сессии на клиенте

```dart
class TokenStorage {
  static const _accessKey = 'access_token';
  static const _refreshKey = 'refresh_token';
  static const _cargoIdKey = 'cargo_id';

  final FlutterSecureStorage _storage;

  Future<void> saveSession({
    required String access,
    required String refresh,
    required int cargoId,
  }) async {
    await _storage.write(key: _accessKey, value: access);
    await _storage.write(key: _refreshKey, value: refresh);
    await _storage.write(key: _cargoIdKey, value: cargoId.toString());
  }

  Future<void> clear() => _storage.deleteAll();
}
```

---

## 7. HTTP-слой (Dio)

### ApiClient с авто-refresh

```dart
class AuthInterceptor extends QueuedInterceptor {
  AuthInterceptor({
    required this.tokenStorage,
    required this.dio,
    required this.onLogout,
  });

  final TokenStorage tokenStorage;
  final Dio dio;
  final VoidCallback onLogout;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) async {
    final access = await tokenStorage.readAccess();
    if (access != null) {
      options.headers['Authorization'] = 'Bearer $access';
    }
    handler.next(options);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) async {
    if (err.response?.statusCode != 401) {
      return handler.next(err);
    }

    final refresh = await tokenStorage.readRefresh();
    if (refresh == null) {
      onLogout();
      return handler.next(err);
    }

    try {
      final response = await dio.post(
        'auth/refresh/',
        data: {'refresh': refresh},
        options: Options(headers: {}), // без Authorization
      );
      final newAccess = response.data['access'] as String;
      final newRefresh = response.data['refresh'] as String;
      await tokenStorage.saveTokens(access: newAccess, refresh: newRefresh);

      err.requestOptions.headers['Authorization'] = 'Bearer $newAccess';
      final retry = await dio.fetch(err.requestOptions);
      return handler.resolve(retry);
    } catch (_) {
      onLogout();
      return handler.next(err);
    }
  }
}
```

### Пример репозитория

```dart
class AuthRepository {
  AuthRepository(this._client);
  final Dio _client;

  Future<AuthResponse> verifyCode(VerifyCodeRequest request) async {
    final response = await _client.post(
      'auth/verify-code/',
      data: request.toJson(),
    );
    return AuthResponse.fromJson(response.data);
  }
}
```

---

## 8. Модели данных (Dart)

### User

```dart
@JsonSerializable()
class User {
  final int id;
  final int cargo;
  final String cargoTitle;
  final String phone;
  final String fullName;
  final int? pickupPoint;
  final String? pickupPointTitle;
  final String? clientCode;
  final String? qrCodeImage;
  final bool isCargoAdmin;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory User.fromJson(Map<String, dynamic> json) => _$UserFromJson(json);
}
```

> `clientCode` — строка **произвольного формата**: карго сам задаёт префикс, номер
> четырёхзначный (`X0001`, `КК0002`), а у старых клиентов остались коды вида `C1234567`.
> Не парсите его и не проверяйте длину/регулярку — показывайте как есть.

### AuthResponse

```dart
@JsonSerializable()
class AuthResponse {
  final String access;
  final String refresh;
  final User user;
  final bool isNewUser;

  factory AuthResponse.fromJson(Map<String, dynamic> json) =>
      _$AuthResponseFromJson(json);
}
```

### Order

```dart
enum OrderSource { pinduoduo, taobao, shop1688, manual }

enum OrderStatus {
  created,
  paid,
  purchased,
  waitingChinaWarehouse,
  arrivedChinaWarehouse,
  cancelled,
}

@JsonSerializable()
class Order {
  final int id;
  final int user;
  final OrderSource source;
  final String sourceDisplayName;
  final String externalOrderId;
  final String productUrl;
  final String productTitle;
  final double? price;
  final int quantity;
  final OrderStatus status;
  final String statusDisplayName;
  final String trackNumber;
  final Map<String, dynamic> rawData;
  final DateTime createdAt;
  final DateTime updatedAt;
}
```

### Parcel

```dart
enum ParcelStatus {
  created,
  purchased,
  waitingChinaWarehouse,
  arrivedChinaWarehouse,
  inStorage,            // legacy, вне авто-цепочки
  sentToKyrgyzstan,     // legacy, вне авто-цепочки
  processing,
  arrivedTopa,
  inTransit,
  arrivedKyrgyzstan,
  atPickupPoint,
  cityDelivery,
  delivered,
  issued,
  cancelled,
  unknown,              // страховка от новых статусов на бэкенде
}

@JsonSerializable()
class Parcel {
  final int id;
  final int user;
  final int? order;
  final String trackNumber;
  final String clientCode;
  final ParcelStatus status;
  final String statusDisplayName;
  final String location;
  final double? weight;
  final double? volume;
  final double? deliveryPrice;   // в сомах (KGS), раньше было в долларах
  final String source;           // pinduoduo | taobao | 1688 | manual
  final String sourceDisplayName;
  final DateTime? arrivedAt;
  final DateTime? issuedAt;
  final DateTime createdAt;
  final DateTime updatedAt;
}
```

### Notification

```dart
enum NotificationType {
  auth,
  orderCreated,
  orderStatusChanged,
  parcelStatusChanged,
  parcelAtPickupPoint,
  cityDeliveryCreated,
  cityDeliveryStatusChanged,
  pinduoduoConnected,
  pinduoduoSynced,
  system,
}

@JsonSerializable()
class AppNotification {
  final int id;
  final String title;
  final String body;
  final NotificationType type;
  final String typeDisplayName;
  final bool isRead;
  final Map<String, dynamic> data;
  final DateTime createdAt;
}
```

### Enum mapping (JSON → Dart)

Backend отдаёт snake_case строки. Пример маппинга:

```dart
ParcelStatus parseParcelStatus(String value) => switch (value) {
      'created' => ParcelStatus.created,
      'purchased' => ParcelStatus.purchased,
      'waiting_china_warehouse' => ParcelStatus.waitingChinaWarehouse,
      'arrived_china_warehouse' => ParcelStatus.arrivedChinaWarehouse,
      'in_storage' => ParcelStatus.inStorage,
      'sent_to_kyrgyzstan' => ParcelStatus.sentToKyrgyzstan,
      'processing' => ParcelStatus.processing,
      'arrived_topa' => ParcelStatus.arrivedTopa,
      'in_transit' => ParcelStatus.inTransit,
      'arrived_kyrgyzstan' => ParcelStatus.arrivedKyrgyzstan,
      'at_pickup_point' => ParcelStatus.atPickupPoint,
      'city_delivery' => ParcelStatus.cityDelivery,
      'delivered' => ParcelStatus.delivered,
      'issued' => ParcelStatus.issued,
      'cancelled' => ParcelStatus.cancelled,
      _ => ParcelStatus.unknown,
    };
```

> ⚠️ **Не бросайте исключение на неизвестном статусе.** Статусы добавляются на бэкенде
> (в этом релизе их прибавилось четыре), и приложение со старым enum падало на парсинге
> списка посылок. Возвращайте `unknown`, а в UI показывайте `status_display_name` —
> сервер всегда присылает готовую подпись на русском.

---

## 9. Справочник API

### Профиль

| Метод | URL | Auth | Описание |
|---|---|---|---|
| GET | `/api/profile/` | да | Текущий пользователь |
| PATCH | `/api/profile/` | да | Обновить `full_name`, `pickup_point` |
| GET | `/api/profile/qr/` | да | `client_code` + URL QR-изображения |
| GET | `/api/profile/notification-preferences/` | да | Настройки уведомлений |
| PATCH | `/api/profile/notification-preferences/` | да | Обновить настройки |

**PATCH /api/profile/:**

```json
{
  "full_name": "Новое Имя",
  "pickup_point": 2
}
```

**GET /api/profile/qr/:**

```json
{
  "client_code": "X0001",
  "qr_code_image": "https://api.example.com/media/qr_codes/X0001.png"
}
```

**Notification preferences:**

```json
{
  "push_enabled": true,
  "parcel_status_enabled": true,
  "order_status_enabled": true,
  "city_delivery_enabled": true,
  "marketing_enabled": false,
  "updated_at": "2026-01-01T12:00:00+06:00"
}
```

---

### Справочники

#### ПВЗ

| Метод | URL | Auth | Описание |
|---|---|---|---|
| GET | `/api/pickup-points/?cargo=<id>` | нет | Список ПВЗ карго-центра |

#### Магазины

| Метод | URL | Auth | Описание |
|---|---|---|---|
| GET | `/api/shops/` | да | Магазины карго пользователя |

**Ответ:**

```json
[
  {
    "id": 1,
    "title": "Pinduoduo",
    "slug": "pinduoduo",
    "icon": "https://api.example.com/media/shop_icons/pdd.png",
    "open_url": "https://mobile.yangkeduo.com/?client_code=X0001",
    "open_type": "webview",
    "client_code": null,
    "instruction": null
  }
]
```

| `open_type` | Действие в Flutter |
|---|---|
| `webview` | `WebViewWidget` внутри приложения |
| `external_app` | `url_launcher` с `LaunchMode.externalApplication` |
| `browser` | `url_launcher` с `LaunchMode.externalApplication` |

| `client_code_strategy` | Поведение |
|---|---|
| `query_param` | `open_url` уже содержит код в URL |
| `clipboard` | `client_code` = код пользователя, скопировать в буфер |
| `manual_instruction` | показать `instruction` с кодом |

#### Тарифы доставки по городу

| Метод | URL | Auth | Описание |
|---|---|---|---|
| GET | `/api/city-delivery-tariffs/` | да | Активные тарифы для ПВЗ пользователя |

---

### Заказы

| Метод | URL | Auth | Описание |
|---|---|---|---|
| GET | `/api/orders/` | да | Список заказов |
| GET | `/api/orders/{id}/` | да | Детали заказа |
| POST | `/api/orders/manual/` | да | Ручное создание |

**Фильтры (query params):**

| Параметр | Пример | Описание |
|---|---|---|
| `status` | `created` | Статус заказа |
| `source` | `pinduoduo` | Источник |
| `track_number` | `LP123` | Трек-номер (частичное совпадение) |
| `date_from` | `2026-01-01` | Дата создания от |
| `date_to` | `2026-01-31` | Дата создания до |

**POST /api/orders/manual/:**

```json
{
  "product_url": "https://example.com/item",
  "product_title": "Товар",
  "price": "1500.00",
  "quantity": 2,
  "track_number": "LP123456"
}
```

**Статусы заказа:**

| Значение | Отображение |
|---|---|
| `created` | Оформлен |
| `paid` | Оплачен |
| `purchased` | Выкуплен |
| `waiting_china_warehouse` | Ожидается на складе в Китае |
| `arrived_china_warehouse` | Прибыл на склад в Китае |
| `cancelled` | Отменён |

---

### Посылки

| Метод | URL | Auth | Описание |
|---|---|---|---|
| GET | `/api/parcels/` | да | Список посылок |
| GET | `/api/parcels/{id}/` | да | Детали |
| GET | `/api/parcels/{id}/history/` | да | История статусов |

**Фильтры:** `status`, `status_in`, `track_number`, `date_from`, `date_to`,
**`source`**, **`source_in`**

**Маркетплейс посылки.** У каждой посылки есть источник — по нему в приложении
делается фильтр «откуда посылка»:

| Поле | Значение |
|---|---|
| `source` | `pinduoduo`, `taobao`, `1688`, `manual` |
| `source_display_name` | готовая подпись: «Pinduoduo», «Taobao», «Вручную» |

Посылка, заведённая сканером на складе (без заказа), приходит как `manual` —
из выдачи она не выпадает.

```
GET /api/parcels/?source=taobao
GET /api/parcels/?source_in=taobao,pinduoduo
GET /api/parcels/                     ← все, без фильтра
```

**Статусы посылки (жизненный цикл):**

```
created → purchased → waiting_china_warehouse → arrived_china_warehouse
  → processing → arrived_topa → in_transit → arrived_kyrgyzstan
  → at_pickup_point → [city_delivery] → delivered → issued
```

От «Прибыл на склад в Китае» до «Прибыл в Кыргызстан» статусы двигает **планировщик
на сервере по времени** — приложению ничего делать не нужно, достаточно перечитывать
список. Дальше статус меняет только оператор при сканировании в ПВЗ.

| Значение | Отображение | Примечание |
|---|---|---|
| `created` | Оформлен | |
| `purchased` | Выкуплен | |
| `waiting_china_warehouse` | Ожидается на складе в Китае | |
| `arrived_china_warehouse` | Прибыл на склад в Китае | старт авто-цепочки |
| `in_storage` | На хранении | legacy, вне авто-цепочки |
| `sent_to_kyrgyzstan` | Отправлен в Кыргызстан | legacy, вне авто-цепочки |
| `processing` | Классификация и обработка | авто |
| `arrived_topa` | Прибыл в Топа | авто, **новый** |
| `in_transit` | В пути | авто |
| `arrived_kyrgyzstan` | Прибыл в Кыргызстан | авто, последний автоматический |
| `at_pickup_point` | В ПВЗ | скан оператора |
| `city_delivery` | Передан на доставку по городу | |
| `delivered` | Доставлен | |
| `issued` | Выдан клиенту | посылка уходит в архив |
| `cancelled` | Отменён | |

`in_storage` и `sent_to_kyrgyzstan` остались у старых посылок — обрабатывать их надо,
но новые в этих статусах не появляются.

**История статуса:**

```json
[
  {
    "id": 1,
    "status": "at_pickup_point",
    "status_display_name": "В ПВЗ",
    "comment": "",
    "changed_by": null,
    "changed_by_phone": null,
    "created_at": "2026-01-15T10:00:00+06:00"
  }
]
```

---

### Адрес доставки в Китае (для заказов на маркетплейсах)

Единый адрес склада в Китае, который клиент вставляет в заказ на PDD/Taobao. Заполняет
супер-владелец в панели, клиент только **читает**. Ответ уже персонализирован: в строке
адреса стоят код карго этого клиента и его личный код — по ним коробку опознают в Китае.

| Метод | URL | Auth | Описание |
|---|---|---|---|
| GET | `/api/delivery-address/` | да | Адрес склада с кодами текущего клиента |

**Ответ (200):**

```json
{
  "recipient_name": "张伟",
  "phone": "13250150777",
  "province": "广东",
  "city": "佛山",
  "district": "南海",
  "detail_address": "里水镇和顺鹤峰1号仓315库",
  "instructions": "Обязательно оставьте свой код в адресе, иначе посылку не опознают.",
  "is_active": true,
  "region": "广东佛山南海",
  "recipient": "张伟",
  "one_line": "程先生 13250150777 广东佛山南海 里水镇和顺鹤峰1号仓315库东 x69610 X0001",
  "detail_address_full": "里水镇和顺鹤峰1号仓315库东",
  "cargo_code": "x69610",
  "client_code": "X0001",
  "updated_at": "2026-08-06T02:15:00+06:00"
}
```

Поля:

- `one_line` — **готовая строка для вставки** в поле адреса на PDD (умное распознавание / 智能填写). Порядок: `收货人 телефон 省市区 детальный_адрес+приписка КОД_КАРГО КОД_КЛИЕНТА`. Оба кода уже внутри, **индекса нет** — маркетплейс подставляет его сам по 省市区.
- `recipient` — 收货人, **ФИО получателя** на складе. Берётся из карго клиента (у каждого карго свой человек на приёмке); если у карго не задано — общее ФИО из настроек адреса, а если и его нет — код клиента.
- `cargo_code` — код карго клиента (`x69610`). Пустая строка, если не задан — тогда его нет и в `one_line`.
- `client_code` — личный код клиента.
- `detail_address_full` — детальный адрес **с припиской карго** (`…仓315库` + `东`). Для ручного заполнения полей берите его, а не `detail_address`.
- `region` — `省市区` слитно, как ожидает распознавание PDD.
- `is_active` — если `false`, адрес ещё не настроен: экран лучше скрыть или показать заглушку.
- `instructions` — памятка от карго, показать рядом с адресом.

> ⚠️ Раньше 收货人 был равен коду клиента. Теперь это обычное ФИО, а **оба кода
> переехали в конец адреса, перед индексом**. Если приложение собирало строку само —
> перестаньте: используйте `one_line`.

**Что сделать в приложении:**

1. Экран «Адрес для заказов в Китае» (в разделе PDD или профиле).
2. `GET /api/delivery-address/` с JWT клиента; при `is_active == false` — «адрес ещё не настроен».
3. Главная кнопка — **«Скопировать»** для `one_line`: клиент вставляет одной строкой, PDD сам разложит по полям.
4. Опционально — копирование полей по отдельности (收货人, телефон, регион, адрес); тогда `cargo_code` и `client_code` нужно дописать в конец детального адреса.
5. Подсветить, что **коды в конце адреса убирать нельзя** — без них коробку не опознают.

```dart
@JsonSerializable()
class DeliveryAddress {
  final String recipient;       // 收货人 = ФИО получателя
  final String oneLine;         // строка для вставки в PDD
  final String region;          // 省市区
  final String phone;
  final String province;
  final String city;
  final String district;
  final String detailAddress;
  final String detailAddressFull;  // адрес + приписка карго
  final String instructions;
  final bool isActive;
  final String cargoCode;       // код карго, может быть пустым
  final String clientCode;
}
```

---

### Доставка по городу

| Метод | URL | Auth | Описание |
|---|---|---|---|
| POST | `/api/city-delivery/estimate/` | да | Предварительный расчёт |
| POST | `/api/city-delivery/` | да | Создать заявку |
| GET | `/api/city-delivery/` | да | Список заявок |
| GET | `/api/city-delivery/{id}/` | да | Детали заявки |

**POST /api/city-delivery/estimate/:**

```json
{ "parcel": 5 }
```

**Ответ:**

```json
{
  "parcel": 5,
  "weight": "2.500",
  "price": "350.00",
  "tariff": {
    "id": 1,
    "title": "Стандарт",
    "base_price": "200.00",
    "price_per_kg": "50.00",
    "free_weight_kg": "1.000",
    "min_price": "200.00",
    "is_default": true,
    "is_active": true,
    "pickup_point": 1,
    "pickup_point_title": "ПВЗ Центральный"
  }
}
```

**POST /api/city-delivery/:**

```json
{
  "parcel": 5,
  "address": "г. Бишкек, ул. Примерная 1, кв. 5",
  "recipient_name": "Иван Иванов",
  "recipient_phone": "+996700000000",
  "comment": "Позвонить за 30 мин",
  "delivery_date": "2026-01-20",
  "delivery_time_slot": "14:00-18:00"
}
```

Цена и тариф рассчитываются **на сервере** автоматически.

**Статусы заявки:**

| Значение | Отображение |
|---|---|
| `created` | Создана |
| `price_calculated` | Стоимость рассчитана |
| `accepted` | Принята |
| `assigned_to_courier` | Назначен курьер |
| `in_delivery` | В доставке |
| `delivered` | Доставлена |
| `cancelled` | Отменена |

**Ограничения:**

- Заявку можно создать только для **своей** посылки
- Нельзя для посылок со статусом `issued`, `delivered`, `cancelled`

---

### Уведомления

| Метод | URL | Auth | Описание |
|---|---|---|---|
| GET | `/api/notifications/` | да | Список |
| GET | `/api/notifications/unread-count/` | да | `{ "count": 3 }` |
| POST | `/api/notifications/{id}/read/` | да | Отметить прочитанным |
| POST | `/api/notifications/read-all/` | да | `{ "updated": 5 }` |
| POST | `/api/device-tokens/` | да | Регистрация FCM-токена |

**POST /api/device-tokens/:**

```json
{
  "token": "fcm_device_token_here",
  "platform": "android"
}
```

| `platform` | Значение |
|---|---|
| iOS | `"ios"` |
| Android | `"android"` |

> Повторная регистрация того же токена обновляет привязку к текущему пользователю (`update_or_create`).

---

### Pinduoduo

| Метод | URL | Auth | Описание |
|---|---|---|---|
| POST | `/api/integrations/pinduoduo/connect/` | да | Подключить аккаунт |
| POST | `/api/integrations/pinduoduo/disconnect/` | да | Отключить |
| POST | `/api/integrations/pinduoduo/sync/` | да | Синхронизировать заказы |
| GET | `/api/integrations/pinduoduo/status/` | да | Статус подключения |

**POST connect:**

```json
{
  "session_data": {
    "cookies": "...",
    "token": "..."
  }
}
```

**GET status:**

```json
{
  "is_connected": true,
  "external_user_id": "pdd_user_123",
  "last_sync_at": "2026-01-10T15:00:00+06:00",
  "last_sync_error": "",
  "created_at": "2026-01-01T12:00:00+06:00",
  "updated_at": "2026-01-10T15:00:00+06:00"
}
```

**POST sync — ответ:**

```json
{
  "synced": 10,
  "created": 3,
  "updated": 7,
  "message": "OK",
  "errors": []
}
```

> Реализация клиента Pinduoduo на сервере настраивается через `PINDUODUO_CLIENT_PATH`. По умолчанию — no-op. Для WebView-парсинга используйте `session_data` из WebView после авторизации пользователя на Pinduoduo.

---

### 9.X Эндпоинты для владельцев карго (роль `is_cargo_admin`)

Доступны только пользователям с ролью владельца/админа карго (JWT того же пользователя; флаг приходит в `/api/profile/`). Клиентам возвращается `403`.

**Сканер посылок (одно поле — трек-номер):**

```
POST /api/parcels/scan/
{ "track_number": "LP00123456789CN" }     // status опционально
```

Ответ `200/201`:

```json
{ "result": "created_pending", "parcel": { "id": 12, "track_number": "...", "status": "arrived_china_warehouse", "user": null } }
```

`result` ∈ `updated` | `created_from_order` | `created_pending`. Трек из чужого карго → `409 {"code": "conflict"}`.

Привязать pending-посылку к клиенту:

```
POST /api/parcels/{id}/assign/
{ "client_code": "X0001" }
```

**Панель управления:**

| Метод | URL | Описание |
|---|---|---|
| GET/POST | `/api/manage/pickup-points/` | список/создание своих ПВЗ |
| GET/PATCH/DELETE | `/api/manage/pickup-points/{id}/` | изменение/удаление ПВЗ |
| GET/POST/PATCH/DELETE | `/api/manage/city-delivery-tariffs/` `…/{id}/` | тарифы доставки |
| GET/PATCH | `/api/manage/cargo/` | профиль своего карго (без `slug`/`code`/`is_active`) |
| GET | `/api/manage/dashboard/` | статистика своего карго |

`GET /api/manage/cargo/` дополнительно отдаёт настройки клиентских кодов:

```json
{
  "price_per_kg_kgs": "306.25",
  "client_code_prefix": "X",
  "client_code_seq": 42,
  "client_code_next": "X0043"
}
```

`client_code_prefix` владелец может менять (уникален на всю платформу),
`client_code_seq` и `client_code_next` — только на чтение.

В `/api/manage/dashboard/` денежные поля переименованы под сомы:
`period_revenue_kgs`, `period_avg_check_kgs`, `issued_revenue_kgs`,
`potential_revenue_kgs` (раньше — те же имена с `_usd`).

### 9.Y Эндпоинт главного владельца (суперпользователь)

```
GET /api/admin/overview/
```

```json
{
  "totals": { "cargo_count": 5, "active_cargo_count": 4, "user_count": 1200, "parcel_count": 8000, "order_count": 9000, "pickup_point_count": 18 },
  "per_cargo": [ { "id": 1, "title": "Карго А", "slug": "cargo-a", "code": "x69610", "is_active": true, "users_count": 300, "parcels_count": 2000, "orders_count": 2200, "pickup_points_count": 5 } ]
}
```

---

## 10. Экраны и навигация

### Рекомендуемая карта экранов

```
Splash
  └── Onboarding (первый запуск)
        └── Auth
              ├── Выбор карго-центра
              ├── Выбор ПВЗ (регистрация)
              ├── Ввод телефона
              ├── Ввод SMS-кода
              └── (успех) → Main
Main (BottomNavigation)
  ├── Home (дашборд)
  │     ├── Активные посылки
  │     ├── Непрочитанные уведомления
  │     └── Быстрые действия
  ├── Orders
  │     ├── Список заказов (фильтры)
  │     ├── Детали заказа
  │     └── Создание ручного заказа
  ├── Parcels
  │     ├── Список посылок (фильтры)
  │     ├── Детали + timeline истории
  │     └── Заказ доставки по городу
  ├── Shops
  │     ├── Список магазинов
  │     ├── Адрес склада в Китае (копировать one_line)
  │     └── WebView / внешний браузер
  └── Profile
        ├── Данные профиля
        ├── QR-код (полноэкранный)
        ├── Адрес склада в Китае (дубль входа — клиенту он нужен часто)
        ├── Настройки уведомлений
        ├── Pinduoduo
        ├── Уведомления (inbox)
        └── Выход
```

### GoRouter — пример

```dart
final router = GoRouter(
  redirect: (context, state) {
    final isLoggedIn = ref.read(authProvider).isAuthenticated;
    final isAuthRoute = state.matchedLocation.startsWith('/auth');
    if (!isLoggedIn && !isAuthRoute) return '/auth/cargo';
    if (isLoggedIn && isAuthRoute) return '/';
    return null;
  },
  routes: [
    GoRoute(path: '/auth/cargo', builder: (_, __) => const CargoSelectScreen()),
    GoRoute(path: '/auth/phone', builder: (_, __) => const PhoneScreen()),
    GoRoute(path: '/auth/code', builder: (_, __) => const OtpScreen()),
    ShellRoute(
      builder: (_, __, child) => MainShell(child: child),
      routes: [
        GoRoute(path: '/', builder: (_, __) => const HomeScreen()),
        GoRoute(path: '/orders', builder: (_, __) => const OrdersScreen()),
        GoRoute(path: '/parcels', builder: (_, __) => const ParcelsScreen()),
        GoRoute(path: '/shops', builder: (_, __) => const ShopsScreen()),
        GoRoute(path: '/profile', builder: (_, __) => const ProfileScreen()),
      ],
    ),
  ],
);
```

### UI-рекомендации по статусам

- Используйте `status_display_name` с сервера — не дублируйте переводы на клиенте
- Timeline посылки: стройте из `/history/`, сортируйте по `created_at` desc
- Цветовая кодировка: зелёный для `at_pickup_point`, синий для «в пути», серый для `cancelled`

---

## 11. Push-уведомления (FCM)

### Настройка Firebase

1. Создайте проект в [Firebase Console](https://console.firebase.google.com/)
2. Добавьте Android (`google-services.json`) и iOS (`GoogleService-Info.plist`)
3. На сервере укажите `FCM_CREDENTIALS_PATH` — путь к service account JSON
4. Без credentials сервер работает в mock-режиме (push не отправляется, in-app уведомления создаются)

> ✅ **Статус на 2026-08-06:** service-account проекта `cargo-dc9d3` установлен на прод,
> сервер отправляет через **FCM HTTP v1** по-настоящему (проверено: Google принимает
> запрос, отклоняет только заведомо невалидный токен). Со стороны бэкенда осталось
> ноль шагов — дальше нужен APNs-ключ в Firebase Console и капабилити в Xcode,
> иначе на iPhone пуши не придут.

### Что сервер кладёт в сообщение

Формат ровно тот, который ждёт приложение:

| Поле | Значение |
|---|---|
| `notification` | всегда присутствует (иначе закрытый iOS ничего не покажет) |
| `data` | только строки; `type` есть всегда |
| `android.priority` | `high` — иначе Doze откладывает доставку |
| `android.notification.channel_id` | `cargo315_default` |
| `apns.headers.apns-priority` | `10` |
| `apns.payload.aps.badge` | число непрочитанных (то же, что `/api/notifications/unread-count/`) |
| `apns.payload.aps.sound` | `default` |

Настройки уведомлений применяются на сервере до отправки: выключенная категория
не даёт ни пуша, ни записи в inbox, `push_enabled: false` гасит только пуш.

Пуш уходит **на все активные токены** пользователя (телефон + планшет).
Токен помечается неактивным только при `UNREGISTERED`, `SENDER_ID_MISMATCH`,
`INVALID_ARGUMENT`, `NOT_FOUND` — временные сбои FCM устройство не отключают.

### Отвязка токена при выходе

```
DELETE /api/device-tokens/     { "token": "<fcm token>" }   → 204
```

Идемпотентно (повторный вызов тоже `204`), чужой токен не удаляет, без `token`
в теле — `400`. Вызывайте вместе с `deleteToken()` в `PushService.onLoggedOut()`.

> Тексты `title`/`body` формирует сервер и **всегда по-русски**: язык пользователя
> в профиле не хранится. Если нужен ky/en — заводим поле языка в профиле, это
> отдельная задача.

### Инициализация в Flutter

```dart
Future<void> setupPushNotifications() async {
  FirebaseMessaging messaging = FirebaseMessaging.instance;

  await messaging.requestPermission(
    alert: true,
    badge: true,
    sound: true,
  );

  final token = await messaging.getToken();
  if (token != null) {
    await deviceTokenRepository.register(
      token: token,
      platform: Platform.isIOS ? 'ios' : 'android',
    );
  }

  FirebaseMessaging.instance.onTokenRefresh.listen((newToken) {
    deviceTokenRepository.register(
      token: newToken,
      platform: Platform.isIOS ? 'ios' : 'android',
    );
  });

  FirebaseMessaging.onMessage.listen(_handleForegroundMessage);
  FirebaseMessaging.onMessageOpenedApp.listen(_handleNotificationTap);
}
```

### Payload push

Сервер отправляет:

- `notification.title` / `notification.body` — для системного баннера
- `data` — строковые key-value. **Все значения — строки** (требование FCM): `parcel_id` придёт как `"7"`, а не `7`.

Ключ `type` есть **всегда** — по нему роутится tap. Для событий по посылке дополнительно приходят `parcel_id`, `track_number`, `status`, `status_display_name`.

```json
{
  "type": "parcel_status_changed",
  "parcel_id": "7",
  "track_number": "LP00123456789CN",
  "status": "in_transit",
  "status_display_name": "В пути"
}
```

Пример обработки tap:

```dart
void _handleNotificationTap(RemoteMessage message) {
  final type = message.data['type'];
  final parcelId = message.data['parcel_id'];

  switch (type) {
    case 'parcel_at_pickup_point':
    case 'parcel_status_changed':
      router.push('/parcels/$parcelId');
    case 'order_created':
    case 'order_status_changed':
      router.push('/orders/${message.data['order_id']}');
    default:
      router.push('/profile/notifications');
  }
}
```

### Когда приходят пуши по посылке

Клиент получает уведомление на каждом шаге пути. Тексты формирует сервер —
показывайте `notification.body` как есть.

| Статус | Заголовок |
|---|---|
| `arrived_china_warehouse` | Посылка на складе в Китае |
| `processing` | Посылка на обработке |
| `arrived_topa` | Посылка прибыла в Топа |
| `in_transit` | Посылка в пути |
| `arrived_kyrgyzstan` | Посылка прибыла в Кыргызстан |
| `at_pickup_point` | Посылка в ПВЗ (`type: parcel_at_pickup_point`) |
| `issued` | Посылка выдана |

Промежуточные статусы двигает планировщик. Если посылка «догоняет» несколько шагов
за один прогон (крон долго не работал), придёт **один** пуш — по итоговому статусу,
а не серия из четырёх. В истории посылки при этом видны все шаги.

Клиент может отключить эту категорию: `parcel_status_enabled: false` в
`/api/profile/notification-preferences/` — тогда не будет ни пуша, ни записи в inbox.

### Синхронизация badge

При открытии приложения:

```dart
final count = await notificationsRepository.unreadCount();
// обновить badge через flutter_app_badger или локальный state
```

---

## 12. Работа с магазинами (WebView / clipboard)

```dart
Future<void> openShop(Shop shop, BuildContext context) async {
  switch (shop.clientCodeStrategy) {
    case ClientCodeStrategy.queryParam:
      await _openUrl(shop.openUrl, shop.openType);
    case ClientCodeStrategy.clipboard:
      await Clipboard.setData(ClipboardData(text: shop.clientCode!));
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Код скопирован в буфер обмена')),
      );
      await _openUrl(shop.openUrl, shop.openType);
    case ClientCodeStrategy.manualInstruction:
      await showDialog(
        context: context,
        builder: (_) => AlertDialog(
          title: const Text('Инструкция'),
          content: Text(shop.instruction ?? ''),
        ),
      );
      await _openUrl(shop.openUrl, shop.openType);
  }
}

Future<void> _openUrl(String url, OpenType type) async {
  switch (type) {
    case OpenType.webview:
      // Navigator.push → ShopWebViewScreen(url: url)
      break;
    case OpenType.externalApp:
    case OpenType.browser:
      await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
  }
}
```

---

## 13. Интеграция Pinduoduo

### Архитектура (важно — проверено экспериментально)

У Pinduoduo **нет публичного API для покупателя**, а запросы защищены анти-ботом
(`anti-content`/`c-kf`/`verifyauthtoken` + проверка TLS-отпечатка). Серверный
парсинг невозможен: бэкенд не может сгенерировать валидную подпись. **Поэтому
парсинг идёт внутри WebView** — страница PDD сама подписывает свои запросы, а мы
лишь **перехватываем ответ** `order_list_v4` и отправляем его на бэкенд. Ничего
ломать/подделывать не нужно.

```
WebView (реальное устройство, юзер залогинен 1 раз)
  → грузит orders.html (можно скрыто/фоном при старте приложения)
  → JS-hook перехватывает ОТВЕТ order_list_v4 (подпись валидна — её делает PDD)
  → Flutter мапит заказы → POST /api/integrations/pinduoduo/ingest/
бэкенд: маппинг → дедуп → авто-создание Parcel по трек-номеру
```

**Ограничения** (озвучить продукту): синк идёт, когда приложение открыто (или
через background-fetch); сессия PDD протухает → при редиректе на логин шлём
`POST /session-expired/` и просим клиента войти заново.

### Рекомендуемый UX

1. Экран «Подключить Pinduoduo» → кнопка открывает WebView с логином.
2. Клиент входит сам (телефон + SMS — PDD обрабатывает капчу/анти-бот).
3. После входа → `POST .../connect/` (просто помечаем подключённым).
4. Дальше при запуске приложения — скрытый WebView грузит заказы и шлёт на `/ingest`.

### Зависимость

Для перехвата сетевых ответов и инъекции скрипта на старте документа используйте
**`flutter_inappwebview`** (у `webview_flutter` нет надёжного перехвата ответов):

```yaml
dependencies:
  flutter_inappwebview: ^6.1.5
```

### Перехват заказов из WebView

```dart
import 'dart:convert';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

// JS-хук: оборачивает fetch и XHR, ловит ответ order_list_v4 и отдаёт его в Flutter.
const _hookJs = r"""
(function () {
  var TARGET = 'order_list_v4';
  function send(body) {
    try { window.flutter_inappwebview.callHandler('pddOrders', body); } catch (e) {}
  }
  var of = window.fetch;
  window.fetch = function () {
    var args = arguments;
    return of.apply(this, args).then(function (resp) {
      try {
        var u = (args[0] && args[0].url) || args[0];
        if (typeof u === 'string' && u.indexOf(TARGET) > -1) resp.clone().text().then(send);
      } catch (e) {}
      return resp;
    });
  };
  var oOpen = XMLHttpRequest.prototype.open;
  var oSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { this.__u = u; return oOpen.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function () {
    var self = this;
    this.addEventListener('load', function () {
      try { if (self.__u && self.__u.indexOf(TARGET) > -1) send(self.responseText); } catch (e) {}
    });
    return oSend.apply(this, arguments);
  };
})();
""";

class PinduoduoSyncWebView extends StatefulWidget {
  const PinduoduoSyncWebView({super.key});
  @override
  State<PinduoduoSyncWebView> createState() => _PinduoduoSyncWebViewState();
}

class _PinduoduoSyncWebViewState extends State<PinduoduoSyncWebView> {
  @override
  Widget build(BuildContext context) {
    return InAppWebView(
      initialUrlRequest: URLRequest(url: WebUri('https://mobile.pinduoduo.com/orders.html')),
      // Инъекция ДО загрузки страницы, чтобы наш хук обернул fetch раньше кода PDD.
      initialUserScripts: UnmodifiableListView([
        UserScript(source: _hookJs, injectionTime: UserScriptInjectionTime.AT_DOCUMENT_START),
      ]),
      onWebViewCreated: (controller) {
        controller.addJavaScriptHandler(
          handlerName: 'pddOrders',
          callback: (args) => _onOrdersJson(args.isNotEmpty ? args.first as String : ''),
        );
      },
      onLoadStop: (controller, url) {
        final u = url?.toString() ?? '';
        // Редирект на логин/проверку → сессия протухла.
        if (u.contains('login.html') || u.contains('psnl_verification')) {
          pinduoduoRepository.markSessionExpired(); // POST /session-expired/
        }
      },
    );
  }

  void _onOrdersJson(String raw) {
    if (raw.isEmpty) return;
    final data = jsonDecode(raw) as Map<String, dynamic>;
    final pdoList = (data['orders'] as List?) ?? const [];
    final orders = pdoList.map(_mapPddOrder).whereType<Map<String, dynamic>>().toList();
    if (orders.isNotEmpty) {
      pinduoduoRepository.ingest(orders); // POST /ingest/ {"orders":[...]}
    }
  }

  // ⚠️ Имена полей PDD сверьте с реальным ответом order_list_v4 в DevTools.
  // Контракт бэкенда стабилен: external_order_id (обяз.), product_title, price,
  // quantity, status, track_number.
  Map<String, dynamic>? _mapPddOrder(dynamic o) {
    if (o is! Map) return null;
    final sn = (o['order_sn'] ?? o['order_id'] ?? '').toString();
    if (sn.isEmpty) return null;
    final goods = (o['order_goods'] ?? o['goods'] ?? o['goods_list']) as List?;
    final firstGoods = (goods != null && goods.isNotEmpty) ? goods.first as Map : const {};
    return {
      'external_order_id': sn,
      'product_title': (firstGoods['goods_name'] ?? '').toString(),
      'price': (o['order_amount'] ?? o['total_amount'])?.toString(),
      'status': (o['order_status'] ?? o['order_status_prompt'] ?? '').toString(),
      'track_number': (o['tracking_number'] ?? o['mail_no'] ?? '').toString(),
      'raw': o,
    };
  }
}
```

Репозиторий-методы — три простых POST на готовые эндпоинты:
`connect()` → `/connect/`, `ingest(orders)` → `/ingest/` с телом `{"orders": [...]}`,
`markSessionExpired()` → `/session-expired/`.

> Сервер сам маппит/дедуплицирует заказы и создаёт `Parcel` по трек-номеру —
> приложению достаточно переслать массив заказов из перехваченного ответа.

---

## 14. Обработка ошибок

### Формат ошибок DRF

**Validation error (400):**

```json
{
  "phone": ["Пользователь не найден в этом карго-центре. Зарегистрируйтесь."],
  "pickup_point_id": ["ПВЗ не принадлежит выбранному карго-центру."]
}
```

**Detail error:**

```json
{ "detail": "Invalid or expired SMS code" }
```

**Throttled (429):**

```json
{ "detail": "SMS code was sent recently" }
```

**Unauthorized (401):**

```json
{ "detail": "Given token not valid for any token type" }
```

### ApiException на клиенте

```dart
class ApiException implements Exception {
  ApiException({
    required this.statusCode,
    this.detail,
    this.fieldErrors = const {},
  });

  final int statusCode;
  final String? detail;
  final Map<String, List<String>> fieldErrors;

  String get userMessage {
    if (detail != null) return detail!;
    if (fieldErrors.isNotEmpty) {
      return fieldErrors.values.first.first;
    }
    return 'Произошла ошибка ($statusCode)';
  }

  factory ApiException.fromDio(DioException e) {
    final data = e.response?.data;
    if (data is Map<String, dynamic>) {
      final fieldErrors = <String, List<String>>{};
      String? detail;
      data.forEach((key, value) {
        if (key == 'detail') {
          detail = value.toString();
        } else if (value is List) {
          fieldErrors[key] = value.map((e) => e.toString()).toList();
        }
      });
      return ApiException(
        statusCode: e.response?.statusCode ?? 0,
        detail: detail,
        fieldErrors: fieldErrors,
      );
    }
    return ApiException(statusCode: e.response?.statusCode ?? 0);
  }
}
```

### Маппинг ошибок для UI

| HTTP | Действие в UI |
|---|---|
| 400 | Показать текст ошибки под полем или SnackBar |
| 401 | Попытка refresh → logout |
| 403 | «Нет доступа» |
| 404 | «Не найдено» |
| 429 | «Подождите минуту перед повторной отправкой» + таймер 60 сек |
| 500+ | «Сервер временно недоступен» + retry |

---

## 15. Локализация и форматы

| Параметр | Значение |
|---|---|
| Язык UI | русский (основной), кыргызский (будущее) |
| Часовой пояс | `Asia/Bishkek` (UTC+6) |
| Формат даты | `dd.MM.yyyy` |
| Формат даты-времени | `dd.MM.yyyy HH:mm` |
| Телефон | `+996 XXX XXX XXX` |
| Валюта | сом (KGS), без символа в API — числовые строки |

```dart
final dateFormat = DateFormat('dd.MM.yyyy HH:mm', 'ru');
final parsed = DateTime.parse(iso8601).toLocal();
```

### Деньги

**Все суммы в API — сомы.** Это касается `delivery_price` посылки, `price` и полей
тарифа в доставке по городу, `price_per_kg_kgs` у карго. Раньше суммы посылок и тариф
карго считались в долларах и в приложении рисовались с «$» — такие места надо найти
и заменить, иначе клиент увидит «$306.25» вместо «306.25 сом».

```dart
final _money = NumberFormat.decimalPatternDigits(locale: 'ru', decimalDigits: 2);

/// «306.25» → «306,25 сом». Пусто/невалидно → прочерк.
String formatMoney(String? raw) {
  final v = double.tryParse(raw ?? '');
  return v == null ? '—' : '${_money.format(v)} сом';
}
```

Суммы приходят **строками** (`DecimalField`) — парсите через `double.tryParse`,
не полагайтесь на то, что JSON отдаст число.

---

## 16. Тестирование

### Unit-тесты

```dart
test('AuthResponse parses correctly', () {
  final json = {
    'access': 'a',
    'refresh': 'r',
    'is_new_user': true,
    'user': { /* ... */ },
  };
  final response = AuthResponse.fromJson(json);
  expect(response.isNewUser, isTrue);
});
```

### Widget-тесты

- OTP-экран: 4 цифры, кнопка активна только при заполнении
- Список посылок: empty state, loading, error

### Integration-тесты

```dart
testWidgets('login flow', (tester) async {
  await tester.pumpWidget(const App(config: AppConfig.dev));
  // выбор карго → телефон → OTP → главный экран
});
```

### Mock API

Используйте `mocktail` + `DioAdapter` или локальный backend с `SMS_BACKEND=mock` (код в логах сервера).

---

## 17. Сборка и публикация

### Android

```bash
flutter build appbundle --flavor prod -t lib/main_prod.dart
```

`AndroidManifest.xml`:

```xml
<uses-permission android:name="android.permission.INTERNET"/>
<uses-permission android:name="android.permission.POST_NOTIFICATIONS"/>
```

Network security (dev):

```xml
<!-- android/app/src/debug/res/xml/network_security_config.xml -->
<network-security-config>
  <domain-config cleartextTrafficPermitted="true">
    <domain includeSubdomains="true">10.0.2.2</domain>
  </domain-config>
</network-security-config>
```

### iOS

```bash
flutter build ipa --flavor prod -t lib/main_prod.dart
```

`Info.plist`:

```xml
<key>NSAppTransportSecurity</key>
<dict>
  <key>NSAllowsArbitraryLoads</key>
  <false/>
</dict>
```

Push capabilities: Background Modes → Remote notifications.

---

## 18. Чеклист перед релизом

### Auth
- [ ] Регистрация с выбором карго и ПВЗ
- [ ] Вход существующего пользователя (`purpose=login`)
- [ ] Авто-refresh токена при 401
- [ ] Logout с blacklist refresh
- [ ] Обработка 429 на send-code (таймер 60 сек)

### Профиль
- [ ] Отображение client_code и QR
- [ ] `client_code` показывается как есть (нет парсинга формата и проверки длины)
- [ ] Смена ФИО и ПВЗ
- [ ] Настройки уведомлений

### Данные
- [ ] Списки заказов и посылок с фильтрами
- [ ] Timeline истории посылки
- [ ] Ручное создание заказа
- [ ] Доставка по городу: estimate → create

### Миграция на новую версию API (обязательно)
- [ ] Все суммы подписаны «сом», нигде не осталось «$»
- [ ] Тариф карго читается из `price_per_kg_kgs` (не `price_per_kg_usd` — поля больше нет)
- [ ] `ParcelStatus` знает `processing`, `arrived_topa`, `in_transit`, `in_storage`
- [ ] Неизвестный статус не роняет парсинг — есть `unknown` + фолбэк на `status_display_name`
- [ ] Экран «Адрес для заказов в Китае»: копирование `one_line`, коды в конце адреса не теряются
- [ ] Повторная регистрация с тем же номером ведёт на вход (`is_new_user: false`), а не в ошибку

### Магазины
- [ ] WebView / external browser по `open_type`
- [ ] Clipboard strategy
- [ ] Manual instruction

### Push
- [ ] Регистрация FCM-токена после login
- [ ] Re-register при `onTokenRefresh`
- [ ] Deep links из push
- [ ] Badge unread count

### Качество
- [ ] Обработка offline (connectivity_plus)
- [ ] Loading / error / empty states на всех экранах
- [ ] Secure storage для токенов
- [ ] Нет hardcoded API URL в prod-сборке
- [ ] ProGuard/R8 rules для release Android

---

## Приложение A. Быстрый старт для разработчика

```bash
# 1. Запустите backend
cd 315CARGO
python manage.py migrate
python manage.py seed_demo
python manage.py runserver

# 2. Создайте Flutter-проект (см. раздел 3)
# 3. Укажите baseUrl = http://10.0.2.2:8000/api/
# 4. Swagger: http://127.0.0.1:8000/api/docs/

# 5. Тестовый flow:
#    GET  /api/cargo-companies/
#    POST /api/auth/send-code/  { phone, cargo_id, purpose: "register" }
#    POST /api/auth/verify-code/ { phone, code, cargo_id, pickup_point_id, full_name }
#    GET  /api/profile/           (Authorization: Bearer ...)
#    GET  /api/delivery-address/  (Authorization: Bearer ...)
```

Если SMS-шлюз недоступен локально, задайте в `.env` резервный код `OTP_MASTER_CODE=<код>` —
он проходит проверку для любого номера, регистрация не блокируется.

## Приложение B. OpenAPI → Dart models

Автогенерация моделей из схемы:

```bash
# Скачать схему
curl http://127.0.0.1:8000/api/schema/ -o openapi.json

# Сгенерировать клиент (openapi-generator)
openapi-generator generate \
  -i openapi.json \
  -g dart-dio \
  -o lib/generated
```

---

*Документ соответствует backend 315CARGO v1.0.0. При изменении API сверяйтесь со Swagger `/api/docs/`.*
