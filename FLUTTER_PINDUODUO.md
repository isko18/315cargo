# Pinduoduo в Flutter — инструкция для клиента 315CARGO

Как реализовать автоматический парсинг заказов Pinduoduo на стороне Flutter.
Документ самодостаточный — бэкенд уже готов.

---

## 1. Главная идея (прочитать обязательно)

У Pinduoduo **нет публичного API для покупателя**, а все запросы защищены
анти-ботом (`anti-content`, `c-kf`, `verifyauthtoken` + проверка TLS-отпечатка).
Это проверено экспериментально:

- сервер **не может** сам тянуть заказы — голый HTTP получает `SUSPECT`/`424`,
  а сгенерировать валидную подпись без браузера нельзя;
- **в настоящем браузере/WebView заказы отдаются** — потому что страница PDD
  сама подписывает свои запросы.

**Вывод:** парсинг делается **внутри WebView**. Мы не подделываем подпись — мы
**перехватываем готовый ответ** запроса `order_list_v4`, который PDD делает сама,
и отправляем его на бэкенд. Бэкенд маппит, дедуплицирует и создаёт посылки.

```
WebView (реальное устройство, клиент залогинен 1 раз)
  → грузит orders.html (видимо при привязке / скрыто при фоновом синке)
  → JS-hook перехватывает ОТВЕТ order_list_v4 (подпись валидна — её сделала PDD)
  → Flutter мапит заказы → POST /api/integrations/pinduoduo/ingest/
бэкенд: маппинг → дедуп → авто-создание Parcel по трек-номеру
```

### Ограничения (сообщить продукту/клиенту)
1. Синк идёт, **когда приложение открыто** (или через background-fetch ОС).
   Чистого «синка при выключенном телефоне» не будет — анти-боту нужен живой
   WebView. Для клиента это всё равно «ничего не делаю»: приложение само дёргает
   скрытый WebView при запуске.
2. **Сессия PDD протухает** (дни–недели). При редиректе на логин шлём
   `POST /session-expired/`, и клиенту приходит уведомление «войдите в PDD заново».

---

## 2. Эндпоинты бэкенда

Все требуют JWT (`Authorization: Bearer <access>`), работают от имени текущего клиента.

| Метод | URL | Назначение |
|---|---|---|
| POST | `/api/integrations/pinduoduo/connect/` | Пометить аккаунт подключённым (после успешного логина в WebView) |
| POST | `/api/integrations/pinduoduo/ingest/` | Прислать перехваченные заказы |
| POST | `/api/integrations/pinduoduo/session-expired/` | Сообщить, что нужен повторный вход |
| GET | `/api/integrations/pinduoduo/status/` | Статус подключения |

**Тело `/ingest/`** — массив заказов в нормализованном виде:
```json
{
  "orders": [
    {
      "external_order_id": "2026...",   // обязательно (номер заказа PDD)
      "product_title": "Куртка",
      "price": "120.00",
      "quantity": 1,
      "status": "shipped",
      "track_number": "LP00...",          // если есть → создастся Parcel
      "raw": { "...": "оригинальный объект заказа PDD" }
    }
  ]
}
```
**Ответ:** `{ "synced": N, "created": N, "updated": N, "errors": [...] }`.

> Маппинг, дедуп и создание `Parcel` по `track_number` делает сервер.
> Приложению достаточно переслать массив заказов.

---

## 3. Зависимость

Нужен **`flutter_inappwebview`** — у `webview_flutter` нет надёжного перехвата
сетевых ответов и инъекции скрипта до загрузки страницы.

```yaml
# pubspec.yaml
dependencies:
  flutter_inappwebview: ^6.1.5
```

Android: убедиться, что в `AndroidManifest.xml` есть `INTERNET` permission (обычно есть).

---

## 4. UX-поток

1. Экран «Подключить Pinduoduo» → кнопка открывает WebView с логином PDD.
2. Клиент входит **сам** (телефон + SMS — капчу/анти-бот обрабатывает сама PDD).
3. После входа (определяем по уходу со страницы логина) → `POST /connect/`,
   закрываем экран, показываем «Подключено».
4. Дальше при каждом запуске приложения (или по таймеру/при заходе на экран
   «Заказы») — **скрытый** WebView грузит `orders.html`, перехватывает заказы и
   шлёт на `/ingest/`.

---

## 5. JS-хук перехвата (вставляется в WebView)

```dart
const pddInterceptHookJs = r"""
(function () {
  var TARGET = 'order_list_v4';   // эндпоинт списка заказов PDD
  function send(body) {
    try { window.flutter_inappwebview.callHandler('pddOrders', body); } catch (e) {}
  }
  // hook fetch
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
  // hook XMLHttpRequest
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
```

Важно: инъекция **до** загрузки страницы (`AT_DOCUMENT_START`), иначе хук не успеет
обернуть `fetch` до того, как код PDD сделает запрос.

---

## 6. Экран привязки (логин)

```dart
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

class PinduoduoConnectScreen extends StatefulWidget {
  const PinduoduoConnectScreen({super.key});
  @override
  State<PinduoduoConnectScreen> createState() => _PinduoduoConnectScreenState();
}

class _PinduoduoConnectScreenState extends State<PinduoduoConnectScreen> {
  bool _connected = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Подключить Pinduoduo')),
      body: InAppWebView(
        initialUrlRequest: URLRequest(
          url: WebUri('https://mobile.pinduoduo.com/login.html'),
        ),
        onLoadStop: (controller, url) async {
          final u = url?.toString() ?? '';
          // Ушли со страницы логина (на личный кабинет/заказы) → вошли успешно.
          final loggedIn = !u.contains('login.html') && !u.contains('psnl_verification');
          if (loggedIn && !_connected) {
            _connected = true;
            await pinduoduoRepository.connect();    // POST /connect/
            if (mounted) Navigator.of(context).pop(true);
          }
        },
      ),
    );
  }
}
```

---

## 7. Фоновый перехват заказов (скрытый WebView)

Вызывать при старте приложения / при открытии экрана «Заказы». WebView может быть
размером 1×1 (скрытый) — заказы перехватываются автоматически.

```dart
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

class PinduoduoSyncWebView extends StatelessWidget {
  const PinduoduoSyncWebView({super.key});

  @override
  Widget build(BuildContext context) {
    // Скрытый 1x1 — клиент его не видит.
    return SizedBox(
      width: 1, height: 1,
      child: InAppWebView(
        initialUrlRequest:
            URLRequest(url: WebUri('https://mobile.pinduoduo.com/orders.html')),
        initialUserScripts: UnmodifiableListView([
          UserScript(
            source: pddInterceptHookJs,
            injectionTime: UserScriptInjectionTime.AT_DOCUMENT_START,
          ),
        ]),
        onWebViewCreated: (controller) {
          controller.addJavaScriptHandler(
            handlerName: 'pddOrders',
            callback: (args) =>
                _onOrdersJson(args.isNotEmpty ? args.first as String : ''),
          );
        },
        onLoadStop: (controller, url) {
          final u = url?.toString() ?? '';
          // Редирект на логин/проверку → сессия протухла.
          if (u.contains('login.html') || u.contains('psnl_verification')) {
            pinduoduoRepository.markSessionExpired(); // POST /session-expired/
          }
        },
      ),
    );
  }

  void _onOrdersJson(String raw) {
    if (raw.isEmpty) return;
    try {
      final data = jsonDecode(raw) as Map<String, dynamic>;
      final list = (data['orders'] as List?) ?? const [];
      final orders =
          list.map(_mapPddOrder).whereType<Map<String, dynamic>>().toList();
      if (orders.isNotEmpty) {
        pinduoduoRepository.ingest(orders); // POST /ingest/
      }
    } catch (_) {/* битый JSON — игнор */}
  }

  // ⚠️ Имена полей PDD сверьте с реальным ответом order_list_v4 в DevTools.
  // Контракт бэкенда стабилен: обязателен external_order_id; остальное опционально.
  Map<String, dynamic>? _mapPddOrder(dynamic o) {
    if (o is! Map) return null;
    final sn = (o['order_sn'] ?? o['order_id'] ?? '').toString();
    if (sn.isEmpty) return null;
    final goods = (o['order_goods'] ?? o['goods'] ?? o['goods_list']) as List?;
    final g = (goods != null && goods.isNotEmpty) ? goods.first as Map : const {};
    return {
      'external_order_id': sn,
      'product_title': (g['goods_name'] ?? '').toString(),
      'price': (o['order_amount'] ?? o['total_amount'])?.toString(),
      'status': (o['order_status'] ?? o['order_status_prompt'] ?? '').toString(),
      'track_number': (o['tracking_number'] ?? o['mail_no'] ?? '').toString(),
      'raw': o,
    };
  }
}
```

---

## 8. Репозиторий (Dio)

```dart
class PinduoduoRepository {
  final Dio dio; // с JWT-интерсептором
  PinduoduoRepository(this.dio);

  Future<void> connect() =>
      dio.post('/api/integrations/pinduoduo/connect/', data: {'session_data': {}});

  Future<Map<String, dynamic>> ingest(List<Map<String, dynamic>> orders) async {
    final r = await dio.post(
      '/api/integrations/pinduoduo/ingest/',
      data: {'orders': orders},
    );
    return Map<String, dynamic>.from(r.data); // {synced, created, updated, errors}
  }

  Future<void> markSessionExpired() =>
      dio.post('/api/integrations/pinduoduo/session-expired/');

  Future<Map<String, dynamic>> status() async {
    final r = await dio.get('/api/integrations/pinduoduo/status/');
    return Map<String, dynamic>.from(r.data);
  }
}
```

---

## 9. Что нужно доделать тебе (Flutter)

1. Подставить реальные имена полей в `_mapPddOrder`: открой `orders.html` в
   мобильном Chrome (DevTools → Network), найди ответ `order_list_v4` и посмотри
   реальную структуру (`order_sn`, `order_status`, `goods`, трек и т.д.).
2. Решить, когда запускать `PinduoduoSyncWebView`: при старте, при заходе на
   «Заказы», по таймеру, или через `workmanager`/background-fetch.
3. На экране «Заказы»/уведомлениях обработать состояние «сессия истекла» (после
   `session-expired` придёт push/in-app уведомление с `data.reason="session_expired"`)
   — показать кнопку «Подключить заново».

---

## 10. Чеклист проверки

- [ ] Логин в WebView проходит (клиент видит свой кабинет PDD).
- [ ] После логина пришёл `POST /connect/` (status → `is_connected: true`).
- [ ] Скрытый WebView ловит ответ `order_list_v4` (JS-handler `pddOrders` срабатывает).
- [ ] `POST /ingest/` вернул `created > 0`, заказы появились в приложении (`/api/orders/`).
- [ ] У заказов с трек-номером появились посылки (`/api/parcels/`).
- [ ] Повторный синк не плодит дубли (`created: 0, updated: N`).
- [ ] При протухшей сессии летит `/session-expired/` и приходит уведомление.
