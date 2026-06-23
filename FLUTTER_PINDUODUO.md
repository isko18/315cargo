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
  flutter_secure_storage: ^9.2.2   # хранение cookies сессии PDD
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

> ⚠️ **Не определяйте вход по URL.** Когда клиент запрашивает SMS-код, PDD
> переводит страницу на промежуточный URL (ввод кода), который уже не содержит
> `login.html` — и наивная проверка «не на логине → вошёл» срабатывает ложно,
> экран закрывается с «Подключено» ещё до ввода кода.
>
> **Надёжный признак входа — появление cookie `PDDAccessToken`** (она есть только
> после успешного логина). Проверяем именно её.

```dart
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

class PinduoduoConnectScreen extends StatefulWidget {
  const PinduoduoConnectScreen({super.key});
  @override
  State<PinduoduoConnectScreen> createState() => _PinduoduoConnectScreenState();
}

class _PinduoduoConnectScreenState extends State<PinduoduoConnectScreen> {
  bool _connected = false;
  final _cookieManager = CookieManager.instance();
  Timer? _poll;

  @override
  void initState() {
    super.initState();
    // Запасной вариант: PDD логинит через AJAX без навигации — события
    // onLoadStop/onUpdateVisitedHistory тогда не приходят. Опрашиваем cookie
    // каждые 2 сек, пока экран открыт.
    _poll = Timer.periodic(const Duration(seconds: 2), (_) => _checkLogin());
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  // Вход подтверждён, только если есть непустой PDDAccessToken.
  Future<bool> _isLoggedIn() async {
    final cookies = await _cookieManager.getCookies(
      url: WebUri('https://mobile.pinduoduo.com'),
    );
    return cookies.any(
      (c) => c.name == 'PDDAccessToken' && (c.value?.toString().isNotEmpty ?? false),
    );
  }

  Future<void> _checkLogin() async {
    if (_connected || !mounted) return;
    if (await _isLoggedIn()) {
      _connected = true;
      _poll?.cancel();
      await PddSession.save();             // сохраняем cookies сессии (см. §8)
      await pinduoduoRepository.connect(); // POST /connect/
      if (mounted) Navigator.of(context).pop(true);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Подключить Pinduoduo')),
      body: InAppWebView(
        initialUrlRequest: URLRequest(
          url: WebUri('https://mobile.pinduoduo.com/login.html'),
        ),
        // Проверяем cookie при загрузке и смене URL; таймер выше — на случай
        // входа без навигации.
        onLoadStop: (controller, url) => _checkLogin(),
        onUpdateVisitedHistory: (controller, url, isReload) => _checkLogin(),
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

class PinduoduoSyncWebView extends StatefulWidget {
  const PinduoduoSyncWebView({super.key});
  @override
  State<PinduoduoSyncWebView> createState() => _PinduoduoSyncWebViewState();
}

class _PinduoduoSyncWebViewState extends State<PinduoduoSyncWebView> {
  bool _ready = false;

  @override
  void initState() {
    super.initState();
    // ВАЖНО: восстановить cookies сессии ДО загрузки страницы, иначе orders.html
    // откроется разлогиненным и редиректнёт на login.
    PddSession.restore().then((_) {
      if (mounted) setState(() => _ready = true);
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!_ready) return const SizedBox.shrink(); // ждём восстановления cookies
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
          } else {
            // PDD мог обновить cookies — пересохраняем, продлевая сессию.
            PddSession.save();
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

  // Маппинг реального ответа order_list_v4 → OrderPayload бэкенда.
  // (поля подставлены по живому ответу PDD; при изменениях PDD скорректировать)
  Map<String, dynamic>? _mapPddOrder(dynamic order) {
    if (order is! Map) return null;
    final sn = (order['order_sn'] ?? '').toString();
    if (sn.isEmpty) return null;

    final goods = (order['order_goods'] as List?) ?? const [];
    // Название: имена всех товаров через " | " (в заказе может быть несколько).
    final title = goods
        .map((g) => (g as Map)['goods_name']?.toString() ?? '')
        .where((s) => s.isNotEmpty)
        .join(' | ');
    // Количество: сумма goods_number по всем товарам.
    final qty = goods.fold<int>(
        0, (s, g) => s + (((g as Map)['goods_number'] as num?)?.toInt() ?? 0));

    // ВАЖНО: суммы у PDD в копейках (фэнях): 81480 → 814.80.
    final amountCents = (order['order_amount'] as num?)?.toInt() ?? 0;

    return {
      'external_order_id': sn,
      'product_title': title.length > 250 ? title.substring(0, 250) : title,
      'price': (amountCents / 100).toStringAsFixed(2),
      'quantity': qty > 0 ? qty : 1,
      'status': _pddStatus(order),
      'track_number': (order['tracking_number'] ?? '').toString(),
      'raw': order, // полный объект заказа → бэкенд сохранит в raw_data
    };
  }

  // Статус PDD → токены бэкенда (SOURCE_STATUS_MAP). Надёжнее всего — по тексту
  // order_status_prompt; число order_status неоднозначно.
  String _pddStatus(Map o) {
    final p = (o['order_status_prompt'] ?? '').toString();
    final track = (o['tracking_number'] ?? '').toString();
    if (p.contains('取消')) return 'cancelled';                          // отменён
    if (p.contains('待付款') || p.contains('待支付')) return 'pending_payment'; // ждёт оплаты
    if (track.isNotEmpty ||
        p.contains('待收货') || p.contains('已发货') || p.contains('运输')) {
      return 'shipped';                                                 // отправлен → в пути
    }
    if (p.contains('完成') || p.contains('成功') && p.contains('交易')) {
      return 'delivered';                                               // получен/завершён
    }
    if (p.contains('待发货') || p.contains('待分享') || p.contains('拼单') ||
        o['pay_status'] == 1) {
      return 'paid';                                                    // оплачен, ждёт отправки
    }
    return 'pending_payment';
  }
}
```

### Поля `order_list_v4` → OrderPayload (по живому ответу)

| PDD | OrderPayload | Примечание |
|---|---|---|
| `order_sn` | `external_order_id` | номер заказа, напр. `260622-129520125451352` |
| `order_goods[].goods_name` | `product_title` | имена всех товаров через ` \| ` |
| `order_goods[].goods_number` | `quantity` | сумма по товарам |
| `order_amount` | `price` | **в копейках** → делить на 100 (`81480` → `814.80`) |
| `tracking_number` | `track_number` | если непусто → бэкенд создаст `Parcel` |
| `order_status_prompt` / `shipping_status` / `pay_status` | `status` | грубый маппинг в `_pddStatus` |
| весь объект | `raw` | сохраняется в `Order.raw_data` |

> В присланном примере все заказы — `交易已取消` (отменены) и без трека, поэтому
> посылки по ним не создаются. У **оплаченных/отправленных** заказов будет
> непустой `tracking_number` → по нему автоматически создастся `Parcel`.
> Доп. поля для будущего: `order_goods[].thumb_url` (картинка), `goods_price`
> (цена за шт. в копейках), `mall.mall_name` (магазин), `order_time` (unix).

---

## 8. Сохранение сессии (cookies) — иначе после перезапуска разлогинит

`PDDAccessToken` обычно **session-cookie без срока жизни** — он не переживает
перезапуск приложения и не всегда виден другому WebView-инстансу. Поэтому после
логина мы **сами сохраняем** cookies PDD в secure storage и **восстанавливаем** их
перед sync-WebView, проставляя срок жизни (превращаем session-cookie в постоянный).

```dart
import 'dart:convert';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class PddSession {
  static const _key = 'pdd_cookies';
  static const _storage = FlutterSecureStorage();
  static final _cm = CookieManager.instance();
  static final _url = WebUri('https://mobile.pinduoduo.com');

  /// Сохранить текущие cookies PDD (вызывать после логина и после каждого синка).
  static Future<void> save() async {
    final cookies = await _cm.getCookies(url: _url);
    if (cookies.isEmpty) return;
    final data = cookies
        .map((c) => {
              'name': c.name,
              'value': c.value,
              'domain': c.domain,
              'path': c.path ?? '/',
              'isSecure': c.isSecure ?? true,
            })
        .toList();
    await _storage.write(key: _key, value: jsonEncode(data));
  }

  /// Восстановить cookies в WebView перед загрузкой orders.html.
  /// Возвращает false, если сохранённой сессии нет.
  static Future<bool> restore() async {
    final raw = await _storage.read(key: _key);
    if (raw == null) return false;
    final list = jsonDecode(raw) as List;
    // Проставляем срок ~30 дней, чтобы cookie стал постоянным и пережил перезапуск.
    final expires = DateTime.now()
        .add(const Duration(days: 30))
        .millisecondsSinceEpoch;
    for (final c in list) {
      final m = c as Map<String, dynamic>;
      if ((m['value'] ?? '').toString().isEmpty) continue;
      await _cm.setCookie(
        url: _url,
        name: m['name'] as String,
        value: m['value'] as String,
        domain: m['domain'] as String?,
        path: (m['path'] as String?) ?? '/',
        expiresDate: expires,
        isSecure: (m['isSecure'] as bool?) ?? true,
      );
    }
    await _cm.flush(); // сбросить cookie store на диск
    return list.isNotEmpty;
  }

  /// Полный сброс (при «отключить Pinduoduo» / протухшей сессии).
  static Future<void> clear() async {
    await _storage.delete(key: _key);
    await _cm.deleteCookies(url: _url);
  }
}
```

Использование:
- в экране логина (§6) — после `connect()` вызвать `PddSession.save()`;
- в sync-WebView (§7) — `PddSession.restore()` в `initState` **до** загрузки;
- после каждого успешного синка — `PddSession.save()` (PDD обновляет cookies → продлеваем сессию);
- при «отключить» / `session-expired` — `PddSession.clear()`.

---

## 9. Репозиторий (Dio)

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

## 10. Что нужно доделать тебе (Flutter)

1. Маппер `_mapPddOrder` уже заполнен по реальному ответу `order_list_v4`
   (см. таблицу полей ниже). Если PDD изменит структуру — скорректировать.
2. Решить, когда запускать `PinduoduoSyncWebView`: при старте, при заходе на
   «Заказы», по таймеру, или через `workmanager`/background-fetch.
3. На экране «Заказы»/уведомлениях обработать состояние «сессия истекла» (после
   `session-expired` придёт push/in-app уведомление с `data.reason="session_expired"`)
   — показать кнопку «Подключить заново».

---

## 11. Чеклист проверки

- [ ] Логин в WebView проходит (клиент видит свой кабинет PDD).
- [ ] После логина пришёл `POST /connect/` (status → `is_connected: true`).
- [ ] **Сессия переживает перезапуск приложения**: закрыть/открыть приложение →
      sync-WebView НЕ редиректит на login (cookies восстановились из storage).
- [ ] Скрытый WebView ловит ответ `order_list_v4` (JS-handler `pddOrders` срабатывает).
- [ ] `POST /ingest/` вернул `created > 0`, заказы появились в приложении (`/api/orders/`).
- [ ] У заказов с трек-номером появились посылки (`/api/parcels/`).
- [ ] Повторный синк не плодит дубли (`created: 0, updated: N`).
- [ ] При протухшей сессии летит `/session-expired/` и приходит уведомление.
