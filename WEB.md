# 315CARGO — документация для веб-панели

Руководство по разработке **веб-панели управления** для backend 315CARGO (Django REST Framework + JWT).
Панель предназначена для двух ролей операторов:

- **Владелец / админ карго** (`is_cargo_admin = true`) — сканер загрузки посылок, управление своими ПВЗ, тарифами, профилем карго, дашборд своего карго-центра.
- **Главный владелец** (`is_superuser = true`) — глобальный дашборд: сколько карго, пользователей, посылок по каждому карго.

> Клиентское мобильное приложение описано в [FLUTTER.md](FLUTTER.md). Здесь — только операторская веб-часть.

---

## Содержание

1. [Обзор и роли](#1-обзор-и-роли)
2. [Базовый URL и окружение](#2-базовый-url-и-окружение)
3. [Аутентификация (JWT)](#3-аутентификация-jwt)
4. [HTTP-слой и автообновление токена](#4-http-слой-и-автообновление-токена)
5. [Маршрутизация по ролям](#5-маршрутизация-по-ролям)
6. [Сканер посылок](#6-сканер-посылок)
7. [Панель владельца карго](#7-панель-владельца-карго)
8. [Дашборд главного владельца](#8-дашборд-главного-владельца)
9. [Обработка ошибок](#9-обработка-ошибок)
10. [Форматы и локализация](#10-форматы-и-локализация)

---

## 1. Обзор и роли

| Роль | Признак в API | Доступ |
|---|---|---|
| Клиент | `is_cargo_admin=false` | только своё (мобильное приложение) |
| Владелец/админ карго | `is_cargo_admin=true` | `/api/manage/*`, сканер, дашборд своего карго |
| Главный владелец | `is_superuser=true` | `/api/admin/overview/` (все карго) |

Скоупинг enforced на сервере: владелец карго **физически не видит и не может менять** данные чужого карго (возвращается `403`/`404`/пустой список). Фронт может доверять серверу, но всё равно должен скрывать недоступные пункты меню по роли.

**Стек (рекомендация):** React + Vite + TypeScript + axios + TanStack Query. Любой SPA-фреймворк подойдёт — API чистый REST/JSON.

---

## 2. Базовый URL и окружение

```
Базовый URL:   https://<your-domain>/api/
Часовой пояс:  Asia/Bishkek
Язык API:      ru-ru
Swagger:       /api/docs/   (если ENABLE_API_DOCS=True)
OpenAPI JSON:  /api/schema/  — можно генерировать типы (openapi-typescript)
```

Генерация TS-типов из схемы:

```bash
npx openapi-typescript https://<your-domain>/api/schema/ -o src/api/schema.d.ts
```

---

## 3. Аутентификация (JWT)

Все операторские эндпоинты требуют заголовок:

```
Authorization: Bearer <access>
```

### 3.1 Вход владельца карго (SMS + JWT)

Владельцы карго входят так же, как клиенты — по номеру телефона своего карго.

```
POST /api/auth/send-code/      { "phone": "+996700000000" }
POST /api/auth/verify-code/    { "phone": "+996700000000", "code": "123456", "cargo": <cargo_id> }
```

Ответ `verify-code`:

```json
{
  "access": "<jwt>",
  "refresh": "<jwt>",
  "user": { "id": 5, "cargo": 1, "cargo_title": "Карго А", "full_name": "...", "is_cargo_admin": true },
  "is_new_user": false
}
```

Фронт проверяет `user.is_cargo_admin === true`. Если `false` — это обычный клиент, в веб-панель его не пускаем.

> `cargo_id` берётся из `GET /api/cargo-companies/` (публичный список карго) — на экране входа оператор выбирает свой карго-центр.

### 3.2 Вход главного владельца (суперпользователь)

⚠️ **Важно:** у суперпользователя нет карго-центра, поэтому SMS-поток (`verify-code` требует `cargo`) ему не подходит. Сейчас в API нет пароль-логина, выдающего JWT. Есть два варианта — согласуйте нужный:

- **A. Включить пароль→JWT эндпоинт** (рекомендуется для веба): добавить стандартные SimpleJWT `TokenObtainPairView`/`TokenRefreshView` на `/api/auth/token/` и `/api/auth/token/refresh/`. Тогда супер логинится телефоном+паролем (заданным через `createsuperuser`). — *Скажите, и я добавлю.*
- **B. Глобальный дашборд смотреть в Django-админке** (`/admin/`) по сессии, а веб-панель оставить только для владельцев карго.

Остальная часть документа описывает API в предположении, что у супера есть валидный `access`-токен (вариант A).

### 3.3 Обновление и выход

```
POST /api/auth/refresh/   { "refresh": "<jwt>" }     → { "access": "...", "refresh": "..." }
POST /api/auth/logout/    { "refresh": "<jwt>" }     → 204  (refresh попадает в blacklist)
```

Токены ротируются: после `refresh` старый `refresh` инвалидируется — **всегда сохраняйте новый**. Срок жизни по умолчанию: `access` 60 мин, `refresh` 30 дней.

---

## 4. HTTP-слой и автообновление токена

Минимальный axios-клиент с единичным обновлением токена при `401`:

```ts
// src/api/client.ts
import axios from "axios";

const api = axios.create({ baseURL: import.meta.env.VITE_API_URL }); // ".../api/"

api.interceptors.request.use((cfg) => {
  const access = localStorage.getItem("access");
  if (access) cfg.headers.Authorization = `Bearer ${access}`;
  return cfg;
});

let refreshing: Promise<string> | null = null;

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const { response, config } = error;
    if (response?.status === 401 && !config._retry) {
      config._retry = true;
      try {
        refreshing ??= axios
          .post(`${api.defaults.baseURL}auth/refresh/`, {
            refresh: localStorage.getItem("refresh"),
          })
          .then((res) => {
            localStorage.setItem("access", res.data.access);
            localStorage.setItem("refresh", res.data.refresh);
            return res.data.access as string;
          })
          .finally(() => (refreshing = null));
        const access = await refreshing;
        config.headers.Authorization = `Bearer ${access}`;
        return api(config);
      } catch {
        localStorage.clear();
        location.href = "/login";
      }
    }
    return Promise.reject(error);
  },
);

export default api;
```

---

## 5. Маршрутизация по ролям

После входа сохраните `user` из ответа `verify-code` (или запросите `GET /api/profile/`).

```ts
if (user.is_cargo_admin) → /panel        // владелец карго
else if (isSuperuser)     → /admin        // главный владелец
else                      → запретить вход (это клиент)
```

`is_superuser` в `/api/profile/` сейчас не отдаётся. Способы определить супера на фронте:
- пробный запрос `GET /api/admin/overview/` (200 → супер, 403 → нет); или
- (если включаете вариант A из §3.2) добавить `is_superuser` в `UserSerializer`. — *Скажите, и я добавлю поле.*

---

## 6. Сканер посылок

Доступно только при `is_cargo_admin=true`. Идея — **одно поле**: оператор сканирует трек-номер (или вводит вручную), посылка загружается автоматически.

### 6.1 Эндпоинт

```
POST /api/parcels/scan/
{ "track_number": "LP00123456789CN" }      // "status" — опционально
```

Логика на сервере:

| Ситуация | `result` | HTTP |
|---|---|---|
| трек уже есть в этом карго | `updated` (статус продвинут до `arrived_china_warehouse`) | 200 |
| есть заказ с таким треком | `created_from_order` (посылка привязана к клиенту) | 201 |
| трек неизвестен | `created_pending` (посылка без клиента — нужно сопоставить) | 201 |
| трек уже в другом карго | — ошибка `{"code":"conflict"}` | 409 |

Ответ:

```json
{
  "result": "created_pending",
  "parcel": {
    "id": 42, "cargo": 1, "user": null, "order": null,
    "track_number": "LP00123456789CN",
    "client_code": "", "status": "arrived_china_warehouse",
    "status_display_name": "Прибыл на склад в Китае",
    "arrived_at": "2026-06-30T12:00:00+06:00", "created_at": "..."
  }
}
```

### 6.2 Привязка непривязанной (pending) посылки к клиенту

Посылки с `user=null` нужно сопоставить с клиентом по его коду:

```
POST /api/parcels/{id}/assign/
{ "client_code": "C1234567" }      → 200 + объект посылки
```

`404`, если клиента с таким кодом нет в карго; `400`, если посылка уже привязана.

### 6.3 Список pending-посылок

Pending-посылки приходят в общий список посылок оператора (видны менеджеру, не видны клиенту). Фильтруйте на фронте по `user === null` либо добавьте бэкенд-фильтр (по запросу).

```
GET /api/parcels/?status=arrived_china_warehouse
```

### 6.4 UX ввода (одно поле)

- **Аппаратный сканер-«клавиатура»** (USB/Bluetooth): эмулирует ввод + `Enter`. Достаточно `<input autofocus>` и сабмита по `Enter` — отправляйте `scan/`, очищайте поле, возвращайте фокус. Можно сканировать пачкой.
- **Камера** (если нужно): библиотеки `@zxing/browser` или `html5-qrcode` дают распознанную строку → тот же `scan/`.

```tsx
function ScanField() {
  const [value, setValue] = useState("");
  const submit = async () => {
    const t = value.trim();
    if (!t) return;
    try {
      const { data } = await api.post("parcels/scan/", { track_number: t });
      toast.success(`${t}: ${data.result}`);
    } catch (e) {
      if (e.response?.status === 409) toast.error("Трек в другом карго");
      else toast.error(e.response?.data?.detail ?? "Ошибка");
    } finally {
      setValue("");           // готово к следующему скану
    }
  };
  return (
    <input autoFocus value={value}
      onChange={(e) => setValue(e.target.value)}
      onKeyDown={(e) => e.key === "Enter" && submit()}
      placeholder="Сканируйте трек-номер" />
  );
}
```

---

## 7. Панель владельца карго

Все эндпоинты ниже требуют `is_cargo_admin=true`, автоматически ограничены своим карго, `cargo` проставляется сервером (передавать не нужно).

### 7.1 ПВЗ

```
GET    /api/manage/pickup-points/
POST   /api/manage/pickup-points/          { "title": "...", "address": "...", "phone"?, "work_schedule"?, "is_active"? }
GET    /api/manage/pickup-points/{id}/
PATCH  /api/manage/pickup-points/{id}/     { любые поля }
DELETE /api/manage/pickup-points/{id}/
```

Объект:

```json
{ "id": 3, "cargo": 1, "title": "ПВЗ Центр", "address": "Бишкек, ...",
  "phone": "+996...", "work_schedule": "Пн-Сб 10:00-19:00", "is_active": true,
  "created_at": "...", "updated_at": "..." }
```

### 7.2 Тарифы доставки по городу

```
GET/POST   /api/manage/city-delivery-tariffs/
GET/PATCH/DELETE /api/manage/city-delivery-tariffs/{id}/
```

Поля: `title`, `base_price`, `price_per_kg`, `free_weight_kg`, `min_price`, `is_default`, `is_active`, `pickup_point` (опц., должен быть из своего карго). `cargo` — read-only.

### 7.3 Профиль своего карго

```
GET    /api/manage/cargo/
PATCH  /api/manage/cargo/      { "title"?, "description"?, "logo"?, "phone"?, "address"? }
```

`slug` и `is_active` менять нельзя (read-only). Для `logo` отправляйте `multipart/form-data`.

### 7.4 Дашборд своего карго

```
GET /api/manage/dashboard/
```

```json
{
  "cargo": { "id": 1, "title": "Карго А", "slug": "cargo-a" },
  "users_count": 320,
  "pickup_points_count": 4,
  "orders_count": 1500,
  "parcels_count": 2100,
  "parcels_pending_count": 7,
  "parcels_by_status": { "arrived_china_warehouse": 120, "at_pickup_point": 30, "issued": 1900 }
}
```

`parcels_pending_count` — сколько непривязанных посылок ждут сопоставления (бейдж в меню сканера).

---

## 8. Дашборд главного владельца

Только `is_superuser`. Карго-владельцу вернётся `403`.

```
GET /api/admin/overview/
```

```json
{
  "totals": {
    "cargo_count": 5,
    "active_cargo_count": 4,
    "user_count": 4200,
    "parcel_count": 38000,
    "order_count": 41000,
    "pickup_point_count": 18
  },
  "per_cargo": [
    { "id": 1, "title": "Карго А", "slug": "cargo-a", "is_active": true,
      "users_count": 320, "parcels_count": 2100, "orders_count": 1500, "pickup_points_count": 4 }
  ]
}
```

Используйте `totals` для карточек-сводки, `per_cargo` — для таблицы/графиков по карго-центрам.

---

## 9. Обработка ошибок

| Код | Значение | Действие на фронте |
|---|---|---|
| 400 | Ошибка валидации / `{"detail","code"}` | показать сообщение из тела |
| 401 | Токен истёк/невалиден | авто-`refresh` (см. §4), иначе на `/login` |
| 403 | Нет прав (не та роль / чужое карго) | скрыть действие, показать «Недостаточно прав» |
| 404 | Объект не найден / вне вашего карго | «Не найдено» |
| 409 | Конфликт (трек в другом карго) | подсказать оператору |

Тело ошибки обычно: `{ "detail": "текст" }`, у сканера дополнительно `{ "code": "conflict" | "invalid" | "no_cargo" }`.

---

## 10. Форматы и локализация

- Даты — ISO 8601 со смещением `+06:00` (Asia/Bishkek). Форматируйте через `Intl.DateTimeFormat("ru-RU", { timeZone: "Asia/Bishkek" })`.
- Денежные/весовые поля (`base_price`, `weight`, …) приходят строками (`DecimalField`) — парсите перед арифметикой.
- Списки сейчас **без пагинации** — возвращается обычный JSON-массив. Если объёмы вырастут, попросите включить пагинацию (`?page=`), и я обновлю этот раздел.
- Статусы посылок отдаются парой `status` (код) + `status_display_name` (готовая русская подпись) — показывайте `status_display_name`.

---

## Сводка эндпоинтов веб-панели

| Метод | URL | Роль |
|---|---|---|
| POST | `/api/auth/send-code/`, `/api/auth/verify-code/`, `/api/auth/refresh/`, `/api/auth/logout/` | все |
| GET | `/api/profile/` | все |
| POST | `/api/parcels/scan/` | владелец карго |
| POST | `/api/parcels/{id}/assign/` | владелец карго |
| GET | `/api/parcels/`, `/api/parcels/{id}/`, `/api/parcels/{id}/history/` | владелец карго |
| CRUD | `/api/manage/pickup-points/` | владелец карго |
| CRUD | `/api/manage/city-delivery-tariffs/` | владелец карго |
| GET/PATCH | `/api/manage/cargo/` | владелец карго |
| GET | `/api/manage/dashboard/` | владелец карго |
| GET | `/api/admin/overview/` | главный владелец |
