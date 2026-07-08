# Модуль Pinduoduo (Flutter)

Готовые Dart-файлы — скопируй папку `pinduoduo/` в свой `lib/`. Полное описание
логики и бэкенда — в корневом `FLUTTER_PINDUODUO.md` и `PINDUODUO_BACKEND.md`.

## 1. Зависимости (`pubspec.yaml`)

```yaml
dependencies:
  flutter_inappwebview: ^6.1.5
  flutter_secure_storage: ^9.2.2
  dio: ^5.0.0
```
Android: в `AndroidManifest.xml` нужен `<uses-permission android:name="android.permission.INTERNET"/>` (обычно уже есть).

## 2. Файлы

| Файл | Что |
|---|---|
| `pdd_api.dart` | `PddApi(dio)` — все запросы (connect/ingest/session-expired/status/parcels) + модель `Parcel` |
| `pdd_js.dart` | JS: хук перехвата `order_list_v4` + авто-проход вкладок со скроллом |
| `pdd_session.dart` | `PddSession` — сохранение/восстановление cookies сессии |
| `pinduoduo_connect_screen.dart` | Экран логина (вход по cookie `PDDAccessToken`) |
| `pinduoduo_sync_screen.dart` | Синк: авто-проход вкладок → перехват → `/ingest` |
| `parcels_screen.dart` | «Мои посылки» — карточки (фото/название/трек/статус/цена) + авто-синк |
| `pinduoduo.dart` | barrel-экспорт |

## 3. Подключение

Создай `Dio` с baseUrl и JWT-интерсептором (как в остальном приложении) и оберни в `PddApi`:

```dart
import 'package:dio/dio.dart';
import 'pinduoduo/pinduoduo.dart';

final dio = Dio(BaseOptions(baseUrl: 'https://315cargo.webtm.ru'))
  ..interceptors.add(InterceptorsWrapper(onRequest: (o, h) {
    o.headers['Authorization'] = 'Bearer $accessToken'; // твой JWT
    h.next(o);
  }));

final pddApi = PddApi(dio);
```

Экран посылок (он же сам запускает синк и содержит кнопку «Подключить Pinduoduo»):

```dart
Navigator.push(context, MaterialPageRoute(
  builder: (_) => ParcelsScreen(api: pddApi),
));
```

Отдельно привязать / синкать вручную:
```dart
await Navigator.push(context, MaterialPageRoute(
  builder: (_) => PinduoduoConnectScreen(api: pddApi)));   // логин
await Navigator.push(context, MaterialPageRoute(
  builder: (_) => PinduoduoSyncScreen(api: pddApi)));      // синк заказов
```

## 4. Поток

1. `ParcelsScreen` открылась → если PDD привязан, автоматически пушит
   `PinduoduoSyncScreen` (мелькнёт «Синхронизация…», сам пройдёт вкладки, отправит
   заказы на `/ingest`, закроется) → список посылок обновится.
2. Не привязан → кнопка «Подключить Pinduoduo» (иконка 🔗) → логин → синк.

## 5. Важное

- **WebView синка виден** (не 1×1) — иначе PDD не грузит список заказов.
- Клики по вкладкам + скролл — **автоматические** (JS), клиент не участвует.
- Разбор заказов (цена/статус/фильтр) — **на сервере**; приложение шлёт сырой
  `data['orders']`. Менять логику → бэкенд `PinduoduoSyncService`.
- Сессия PDD одна на аккаунт: вход в наш WebView выкидывает офиц. приложение PDD.
  При протухании летит `/session-expired/` → покажи «Подключить заново».
