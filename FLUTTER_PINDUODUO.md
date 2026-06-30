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
  InAppWebViewController? _controller;
  Timer? _poll;

  @override
  void initState() {
    super.initState();
    _poll = Timer.periodic(const Duration(seconds: 2), (_) => _checkLogin());
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  // Вход подтверждён, если есть непустой PDDAccessToken (или pdd_user_id).
  // ВАЖНО: на iOS обязательно передавать webViewController, иначе getCookies
  // читает из пустого общего хранилища и всегда вернёт [].
  Future<bool> _isLoggedIn() async {
    if (_controller == null) return false;
    final cookies = await _cookieManager.getCookies(
      url: WebUri('https://mobile.pinduoduo.com'),
      webViewController: _controller, // ← ключевая правка
    );
    // ДИАГНОСТИКА: видно в консоли, какие cookies реально пришли.
    debugPrint('PDD cookies: ${cookies.map((c) => c.name).toList()}');
    bool has(String n) =>
        cookies.any((c) => c.name == n && (c.value?.toString().isNotEmpty ?? false));
    return has('PDDAccessToken') || has('pdd_user_id');
  }

  Future<void> _finish() async {
    if (_connected || !mounted) return;
    _connected = true;
    _poll?.cancel();
    await PddSession.save(_controller);   // сохраняем cookies сессии (см. §8)
    await pinduoduoRepository.connect();  // POST /connect/
    if (mounted) Navigator.of(context).pop(true);
  }

  Future<void> _checkLogin() async {
    if (_connected || !mounted) return;
    if (await _isLoggedIn()) await _finish();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Подключить Pinduoduo'),
        actions: [
          // Фолбэк: если авто-детект не сработал, но клиент видит, что вошёл.
          TextButton(
            onPressed: _finish,
            child: const Text('Готово', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
      body: InAppWebView(
        initialUrlRequest: URLRequest(
          url: WebUri('https://mobile.pinduoduo.com/login.html'),
        ),
        onWebViewCreated: (c) => _controller = c,
        onLoadStop: (controller, url) => _checkLogin(),
        onUpdateVisitedHistory: (controller, url, isReload) => _checkLogin(),
      ),
    );
  }
}
```

---

## 7. Sync-экран (перехват заказов)

> ⚠️ **Два критичных момента, иначе заказы не приходят:**
> 1. WebView должен быть **видимого/нормального размера** (НЕ `1×1`). На 1×1 PDD
>    ленится грузить список заказов (lazy-load по видимости) → `order_list_v4` не
>    вызывается.
> 2. Надо **кликнуть по вкладкам** (待收货 «в пути», 待发货 «ждёт отправки»). PDD
>    отдаёт активные заказы только на их вкладках; во «全部» могут быть одни
>    отменённые. У вкладки бывает **бейдж** («待收货1») — клик ищем по «начинается с».

Вызывать с экрана «Обновить заказы PDD» (синк по требованию).

```dart
import 'dart:async';
import 'dart:convert';
import 'dart:collection';
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

// JS: кликает по вкладкам заказов, чтобы PDD дёрнул order_list_v4 для активных.
const _pddClickTabsJs = r"""
(function(tabs){
  var i = 0;
  function clickTab(t){
    var els = document.querySelectorAll('div,span,a,li');
    for (var k=0;k<els.length;k++){
      var el = els[k];
      var txt = (el.textContent||'').trim();
      // вкладка: текст начинается с названия, короткий (допускаем бейдж "1"), видимый
      if (txt.indexOf(t)===0 && txt.length <= t.length+3 && el.offsetParent!==null){
        el.click(); return true;
      }
    }
    return false;
  }
  function step(){ if (i<tabs.length){ clickTab(tabs[i]); i++; setTimeout(step, 1800);} }
  step();
})(['待收货','待发货','全部']);
""";

class PinduoduoSyncScreen extends StatefulWidget {
  const PinduoduoSyncScreen({super.key});
  @override
  State<PinduoduoSyncScreen> createState() => _PinduoduoSyncScreenState();
}

class _PinduoduoSyncScreenState extends State<PinduoduoSyncScreen> {
  InAppWebViewController? _c;
  bool _ready = false, _done = false;
  int _created = 0;
  String _status = 'Загружаю заказы…';
  Timer? _timeout;

  @override
  void initState() {
    super.initState();
    // Восстановить cookies ДО загрузки, иначе orders.html уйдёт на login.
    PddSession.restore().then((_) {
      if (mounted) setState(() => _ready = true);
    });
    _timeout = Timer(const Duration(seconds: 45), _finish); // общий лимит
  }

  @override
  void dispose() { _timeout?.cancel(); super.dispose(); }

  void _finish() {
    if (_done || !mounted) return;
    _done = true; _timeout?.cancel();
    Navigator.of(context).pop(true);
  }

  Future<void> _onOrders(String raw) async {
    if (raw.isEmpty || _done) return;
    try {
      final data = jsonDecode(raw) as Map<String, dynamic>;
      final orders =
          (data['orders'] as List?)?.cast<Map<String, dynamic>>() ?? const [];
      if (orders.isEmpty) return;
      setState(() => _status = 'Найдено: ${orders.length}, сохраняю…');
      // Шлём СЫРЫЕ заказы — сервер сам парсит цену/статус и фильтрует.
      final r = await pinduoduoRepository.ingest(orders); // POST /ingest/
      _created += (r['created'] as int? ?? 0);
      await PddSession.save(_c);
      setState(() => _status = 'Сохранено новых: $_created');
    } catch (_) {/* битый JSON — игнор */}
  }

  @override
  Widget build(BuildContext context) {
    if (!_ready) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    return Scaffold(
      appBar: AppBar(
        title: Text(_status),
        actions: [TextButton(
          onPressed: _finish,
          child: const Text('Готово', style: TextStyle(color: Colors.white)),
        )],
      ),
      // ВАЖНО: реальный размер, не 1×1 — иначе список не грузится.
      body: InAppWebView(
        initialUrlRequest:
            URLRequest(url: WebUri('https://mobile.pinduoduo.com/orders.html')),
        initialUserScripts: UnmodifiableListView([
          UserScript(source: pddInterceptHookJs,
              injectionTime: UserScriptInjectionTime.AT_DOCUMENT_START),
        ]),
        onWebViewCreated: (c) {
          _c = c;
          c.addJavaScriptHandler(handlerName: 'pddOrders',
              callback: (a) => _onOrders(a.isNotEmpty ? a.first as String : ''));
        },
        onLoadStop: (controller, url) async {
          final u = url?.toString() ?? '';
          if (u.contains('login.html') || u.contains('psnl_verification')) {
            await pinduoduoRepository.markSessionExpired(); // сессия слетела
            _finish();
            return;
          }
          await PddSession.save(_c);            // продлеваем сессию
          // Кликаем вкладки → PDD отдаёт order_list_v4 активных заказов.
          await controller.evaluateJavascript(source: _pddClickTabsJs);
        },
      ),
    );
  }
}
```

> Открываешь этот экран кнопкой «Обновить заказы PDD»; он грузит orders.html,
> прокликивает вкладки, ловит `order_list_v4` и шлёт **сырые** заказы на `/ingest`.
> Сервер сам парсит цену (`order_amount/100`), статус (`order_status_prompt`),
> **фильтрует** (только ждёт отправки / в пути / получен, отменённые — нет) и
> создаёт `Parcel` по `tracking_number`. Менять логику разбора → бэкенд,
> `PinduoduoSyncService._normalize_pdd_order` (пересборка приложения не нужна).

> **Разбор заказов теперь на сервере.** Приложение НЕ мапит поля — шлёт сырой
> массив `orders` из `order_list_v4`. Сервер делает: цена `order_amount/100`,
> статус по `order_status_prompt`, **фильтр** (берёт только «ждёт отправки» и
> «в пути», отбрасывает отменённые/неоплаченные/завершённые), создаёт `Parcel`
> по `tracking_number`. Это значит: правки логики разбора не требуют пересборки
> приложения. Если нужно менять, какие статусы сохранять — это в бэкенде,
> `PinduoduoSyncService._normalize_pdd_order`.

### Поля `order_list_v4`, которые читает сервер

| PDD | Order | Примечание |
|---|---|---|
| `order_sn` | `external_order_id` | номер заказа, напр. `260622-129520125451352` |
| `order_goods[].goods_name` | `product_title` | имена всех товаров через ` \| ` |
| `order_goods[].goods_number` | `quantity` | сумма по товарам |
| `order_amount` | `price` | **в копейках** → делить на 100 (`81480` → `814.80`) |
| `tracking_number` | `track_number` | если непусто → бэкенд создаст `Parcel` |
| `order_status_prompt` | `status` | по тексту: 待发货→`paid`, 待收货/已发货→`shipped` (`PURCHASED`) |
| весь объект | `raw_data` | сохраняется целиком |

**Фильтр на сервере** (`_normalize_pdd_order`): сохраняются только заказы со
статусом `待发货` (ждёт отправки) и `待收货/已发货/运输` (в пути). Отбрасываются:
`交易已取消` (отменён), `待付款/待支付` (не оплачен), `退款` (возврат) и завершённые.

**Заказ = посылка.** Для каждого сохранённого заказа создаётся `Parcel` (одна на
заказ). Идентификатор посылки — реальный `tracking_number`; пока его нет (заказ
ждёт отправки) используется номер заказа `order_sn`, а когда придёт реальный
трек — он автоматически заменяет временный.

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
  /// На iOS обязательно передавать controller, иначе getCookies вернёт [].
  static Future<void> save([InAppWebViewController? controller]) async {
    final cookies =
        await _cm.getCookies(url: _url, webViewController: controller);
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
