# 315CARGO — что обновить в мобильном приложении

Изменения бэкенда, которые касаются **клиентского** Flutter-приложения. Web-панель
(сотрудники/владельцы) сюда не входит.

Кратко:
1. **НОВОЕ:** адрес доставки в Китай для PDD — `GET /api/delivery-address/`.
2. **Статусы посылок:** добавлены 3 новых статуса + авто-цепочка теперь реально идёт.
3. Поле `pickup_point` у посылки.

---

## 0. Ссылки-приглашения карго — домен изменился

> ⛔ **Домен в ТЗ (`315cargo.webtm.ru`) устарел.** Ссылки живут на **`315cargo.com`**.

Бэкенд отдаёт:

| URL | Что |
|---|---|
| `https://315cargo.com/.well-known/assetlinks.json` | Android App Links, `200`, `application/json` |
| `https://315cargo.com/.well-known/apple-app-site-association` | iOS Universal Links, без расширения |
| `https://315cargo.com/j/<slug>` | страница-заглушка: логотип, название, код карго, кнопка «Открыть в приложении», ссылка на Play |

Содержимое обоих `.well-known` — ровно как в ТЗ (package `com.cargo315.app`,
appID `Y37HNJ3WU3.com.cargo315.app`, паттерн `/j/*`), домен внутри них не упоминается.

**Что поменять в приложении:**

- `AndroidManifest.xml` — в intent-filter хост `315cargo.webtm.ru` → **`315cargo.com`**
- `ios/Runner/Runner.entitlements` — `applinks:315cargo.webtm.ru` → **`applinks:315cargo.com`**
  (и подключить Associated Domains через Xcode UI, как описано в ТЗ)
- Схема `cargo315://join/<slug>` не меняется — работает без верификации домена

Регистр slug не важен: `/j/315CARGO` и `/j/315cargo` открывают одно и то же.
Неизвестный или отключённый slug → `404` со страницей «Такого карго нет».

---

## 1. Адрес доставки (Китай/PDD) — НОВОЕ, приоритет

Единый адрес склада в Китае, который клиент вставляет в PDD при оформлении заказа.
Заполняет супер-владелец в панели; клиент только **читает**. В строке адреса уже
вшиты **код карго** и **код текущего клиента** — они стоят в конце, перед индексом;
по ним в Китае опознают коробку. Имя получателя (收货人) — обычное ФИО со склада.

> ⚠️ **Изменено 2026-08-06 (пуши по посылке):** клиент теперь получает уведомление на
> каждом шаге пути (обработка → Топа → в пути → прибыл в КР), раньше авто-статусы молчали
> и первый пуш приходил только в ПВЗ. Если посылка догоняет несколько шагов за один
> прогон — придёт один пуш по итоговому статусу. В `data` пуша теперь всегда есть `type`
> (раньше его не было, и роутинг tap по нему не работал) плюс `parcel_id`,
> `track_number`, `status`, `status_display_name` — все значения строками.

> ⚠️ **Изменено 2026-08-06 (валюта):** панель и расчёты перешли с доллара на **сом (KGS)**.
> `delivery_price` у посылки теперь в сомах — в приложении нужно убрать «$» и писать «сом».
> Тариф карго переименован: `price_per_kg_usd` → **`price_per_kg_kgs`** (в `/api/cargos/`).
> Существующие суммы пересчитаны по курсу разово командой на сервере.

> ⚠️ **Изменено 2026-08-06 (формат кода клиента):** коды клиентов больше не случайные
> (`C` + 7 цифр), а последовательные: префикс карго + 4-значный номер — `X0001`, `X0002`.
> Префикс задаёт владелец карго и он уникален на платформе. Уже выданные коды не менялись,
> поэтому в приложении по-прежнему нельзя предполагать длину или формат кода — берите
> `client_code` как есть.

> ⚠️ **Изменено 2026-08-06:** раньше 收货人 = код клиента. Теперь 收货人 = ФИО, а коды
> переехали в конец адреса, перед индексом. Порядок в `one_line`:
> `ФИО телефон 省市区 детальный_адрес КОД_КАРГО КОД_КЛИЕНТА индекс`.
> Код карго — общий для всех клиентов одного карго-центра, задаётся супер-владельцем.

### Эндпоинт

| Метод | URL | Auth | Описание |
|---|---|---|---|
| GET | `/api/delivery-address/` | да (любой залогиненный клиент) | Адрес склада с кодом этого клиента |

> PUT/PATCH — только супер-владелец (панель). Мобилке не нужен.

### Ответ (200)

```json
{
  "recipient_name": "张伟",
  "phone": "+8613800138000",
  "province": "广东省",
  "city": "广州市",
  "district": "白云区",
  "detail_address": "XX路 100号 315CARGO仓库",
  "postal_code": "510000",
  "instructions": "Обязательно оставьте свой код в адресе, иначе посылку не опознают.",
  "is_active": true,
  "region": "广东省广州市白云区",
  "recipient": "张伟",
  "one_line": "张伟 +8613800138000 广东省广州市白云区 XX路 100号 315CARGO仓库 x69610 C1234567 510000",
  "cargo_code": "x69610",
  "client_code": "C1234567",
  "updated_at": "2026-08-01T02:15:00Z"  
}
```

Поля:
- `recipient` — **收货人 = ФИО получателя** на складе. Именно это идёт в имя получателя в PDD. Если ФИО в панели не заполнено, сюда фолбэком приходит код клиента.
- `one_line` — **готовая строка для вставки** в PDD (умное распознавание / 智能填写): `收货人 телефон 省市区 детальный_адрес КОД_КАРГО КОД_КЛИЕНТА индекс`. Оба кода уже внутри, перед индексом.
- `cargo_code` — **код карго клиента** (напр. `x69610`), новое поле. Пустая строка, если супер-владелец его ещё не задал — тогда его нет и в `one_line`.
- `region` — `省市区` одной строкой (провинция+город+район слитно).
- `phone`, `province`, `city`, `district`, `detail_address`, `postal_code` — по отдельности (для ручного заполнения полей PDD).
- `instructions` — памятка клиенту (показать рядом).
- `is_active` — если `false`, адрес не готов: экран лучше скрыть/задизейблить.
- `recipient_name` — сырое ФИО из панели; для показа клиенту используйте `recipient` (он с фолбэком).
- `client_code` — код текущего клиента отдельным полем (для ручного заполнения полей PDD: вместе с `cargo_code` дописывается в конец детального адреса).

### Что сделать в приложении

1. Экран/блок «Адрес для заказов в PDD» (в разделе PDD или профиле).
2. Дёрнуть `GET /api/delivery-address/` (JWT клиента).
3. Если `is_active == false` → показать «адрес ещё не настроен».
4. Показать поля + `instructions`. Дать кнопку **«Скопировать»**:
   - основная — копирует `one_line` (клиент вставляет одной строкой в 收货地址 → PDD сам разложит по полям);
   - опционально — копировать поля по отдельности (收货人=`recipient`, телефон, регион, адрес + `cargo_code` и `client_code` в конце адреса).
5. Подсветить, что **коды в конце адреса** убирать нельзя — без них коробку не опознают.

### Модель (Dart)

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
  final String postalCode;
  final String instructions;
  final bool isActive;
  final String cargoCode;       // код карго (может быть пустым)
  final String clientCode;
  DeliveryAddress(/* ... */);
  factory DeliveryAddress.fromJson(Map<String, dynamic> json) => _$DeliveryAddressFromJson(json);
}
```

---

## 2. Статусы посылок — добавлены новые + авто-цепочка

### Новые статусы (backend snake_case)

В `ParcelStatus` добавьте **3 статуса** (сейчас в мобильной enum их нет — при их
получении текущий парсер кинет `ArgumentError`):

| Backend | Dart enum | Отображение (RU) |
|---|---|---|
| `in_storage` | `inStorage` | Отправлен на хранение |
| `in_transit` | `inTransit` | В пути |
| `processing` | `processing` | Классификация и обработка |

Полный список статусов сейчас:
`created`, `purchased`, `waiting_china_warehouse`, `arrived_china_warehouse`,
**`in_storage`**, `sent_to_kyrgyzstan`, **`in_transit`**, `arrived_kyrgyzstan`,
**`processing`**, `at_pickup_point`, `city_delivery`, `delivered`, `issued`, `cancelled`.

```dart
enum ParcelStatus {
  created,
  purchased,
  waitingChinaWarehouse,
  arrivedChinaWarehouse,
  inStorage,          // НОВОЕ
  sentToKyrgyzstan,
  inTransit,          // НОВОЕ
  arrivedKyrgyzstan,
  processing,         // НОВОЕ
  atPickupPoint,
  cityDelivery,
  delivered,
  issued,
  cancelled,
}

ParcelStatus parseParcelStatus(String value) => switch (value) {
      'created' => ParcelStatus.created,
      'purchased' => ParcelStatus.purchased,
      'waiting_china_warehouse' => ParcelStatus.waitingChinaWarehouse,
      'arrived_china_warehouse' => ParcelStatus.arrivedChinaWarehouse,
      'in_storage' => ParcelStatus.inStorage,
      'sent_to_kyrgyzstan' => ParcelStatus.sentToKyrgyzstan,
      'in_transit' => ParcelStatus.inTransit,
      'arrived_kyrgyzstan' => ParcelStatus.arrivedKyrgyzstan,
      'processing' => ParcelStatus.processing,
      'at_pickup_point' => ParcelStatus.atPickupPoint,
      'city_delivery' => ParcelStatus.cityDelivery,
      'delivered' => ParcelStatus.delivered,
      'issued' => ParcelStatus.issued,
      'cancelled' => ParcelStatus.cancelled,
      // на будущее лучше не кидать исключение, а вернуть fallback:
      _ => ParcelStatus.created,
    };
```

> **Важно:** сервер может добавлять статусы и дальше — в `parseParcelStatus`
> сделайте безопасный `_ => <fallback>` вместо `throw`, иначе новые статусы будут
> ронять экран трекинга.

### Порядок для таймлайна трекинга

`arrived_china_warehouse → in_storage → sent_to_kyrgyzstan → in_transit →
arrived_kyrgyzstan → processing → at_pickup_point → issued`.
(`city_delivery`/`delivered` — ветка доставки по городу.)

### Поведение

Промежуточные статусы (`in_storage`, `in_transit`, `processing` и т.д.) теперь
проставляются **автоматически по времени** после приёма на складе в Китае. Клиент
будет получать `parcelStatusChanged`-уведомления и видеть смену статуса в трекинге
без действий оператора. Отдельных экранов не требуется — просто корректно
показывать все статусы в истории/таймлайне.

---

## 3. Поле `pickup_point_title` у посылки

У посылки на бэкенде появился **физический ПВЗ приёмки** — куда её реально приняли.
Клиенту (в `/api/parcels/`) отдаётся **только название** этого ПВЗ; числовой id
клиентам не выдаётся.

- `pickup_point_title` — `String?` — название ПВЗ, где посылка (физический ПВЗ
  приёмки; если ещё не принята — ПВЗ из профиля клиента; иначе `null`).

Мобилке достаточно, при желании, показать `pickup_point_title` на статусе «В ПВЗ»
(«Заберите в: …»). Обязательных изменений нет — поле опциональное.

Добавьте в модель `Parcel`:
```dart
final String? pickupPointTitle; // название ПВЗ (для отображения)
```

---

## Чеклист мобилки

- [ ] Экран «Адрес для PDD» → `GET /api/delivery-address/`, кнопка «Скопировать» (`one_line`), учёт `is_active`, показ `instructions`.
- [ ] `ParcelStatus`: добавить `in_storage`, `in_transit`, `processing` + подписи.
- [ ] `parseParcelStatus`: fallback вместо `throw` на неизвестный статус.
- [ ] Таймлайн трекинга: показать промежуточные авто-статусы в правильном порядке.
- [ ] (Опц.) `Parcel.pickup_point_title` в модели и на экране «В ПВЗ».
