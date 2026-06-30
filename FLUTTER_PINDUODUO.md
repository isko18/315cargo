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
  → грузит orders.html (видимый sync-экран) и КЛИКАЕТ вкладки 待收货/待发货
  → JS-hook перехватывает ОТВЕТ order_list_v4 (подпись валидна — её сделала PDD)
  → Flutter шлёт СЫРЫЕ заказы → POST /api/integrations/pinduoduo/ingest/
бэкенд: разбор → фильтр → дедуп → авто-создание Order + Parcel
```

### Ограничения (сообщить продукту/клиенту)
1. Синк идёт, **когда приложение открыто** (синк по требованию — кнопка
   «Обновить заказы PDD»). Анти-боту нужен живой WebView, чистого фонового синка
   при выключенном телефоне не будет.
2. **Сессия PDD протухает** (дни–недели) + у PDD **одна активная сессия на
   аккаунт** — вход в наш WebView выкидывает офиц. приложение PDD, и наоборот.
   При редиректе на логин шлём `POST /session-expired/` и просим войти заново.

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
3. После входа (определяем по cookie `PDDAccessToken`) → `POST /connect/`,
   закрываем экран, показываем «Подключено».
4. Кнопка **«Обновить заказы PDD»** открывает `PinduoduoSyncScreen` (§7): он
   грузит `orders.html`, **кликает вкладки** активных заказов, перехватывает
   `order_list_v4` и шлёт на `/ingest/`.

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

// JS: АВТОМАТИЧЕСКИ проходит вкладки заказов + скроллит каждую (грузит все
// страницы), чтобы PDD сам сделал order_list_v4 для всех активных заказов.
// Клиент ничего не нажимает — всё делает скрипт.
const _pddAutoSyncJs = r"""
(function(tabs){
  var i = 0;
  function clickTab(t){
    var els = document.querySelectorAll('div,span,a,li');
    for (var k=0;k<els.length;k++){
      var el = els[k], txt = (el.textContent||'').trim();
      // вкладка: текст начинается с названия, короткий (бейдж "1" ок), видимый
      if (txt.indexOf(t)===0 && txt.length <= t.length+3 && el.offsetParent!==null){
        el.click(); return true;
      }
    }
    return false;
  }
  function scroll(n, cb){
    var k=0;
    var iv=setInterval(function(){
      window.scrollTo(0, document.body.scrollHeight);
      window.dispatchEvent(new Event('scroll'));
      if(++k>=n){ clearInterval(iv); cb&&cb(); }
    }, 700);
  }
  function step(){
    if(i<tabs.length){ clickTab(tabs[i]); i++; setTimeout(function(){ scroll(4, step); }, 1200); }
  }
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
          // Авто: проходим вкладки + скроллим → PDD отдаёт order_list_v4 всех заказов.
          await controller.evaluateJavascript(source: _pddAutoSyncJs);
        },
      ),
    );
  }
}
```

> Экран грузит orders.html, **сам** проходит вкладки + скроллит (клиент ничего не
> нажимает), ловит `order_list_v4` и шлёт **сырые** заказы на `/ingest`. Сервер
> сам парсит цену (`order_amount/100`), статус (`order_status_prompt`),
> **фильтрует** (ждёт отправки / в пути / получен — да; отменённые — нет) и
> создаёт `Parcel` по `tracking_number`. Приложение поля НЕ мапит. Менять логику
> разбора → бэкенд, `PinduoduoSyncService._normalize_pdd_order` (без пересборки).

### Авто-запуск (без кнопки)

Чтобы синк шёл сам при заходе на «Заказы»/«Посылки» (клиент один раз привязал —
дальше ничего не делает):

```dart
@override
void initState() {
  super.initState();
  WidgetsBinding.instance.addPostFrameCallback((_) => _autoSyncPdd());
}

Future<void> _autoSyncPdd() async {
  try {
    final st = await pinduoduoRepository.status();
    if (st['is_connected'] != true || !mounted) return;   // не подключён — пропуск
    await Navigator.push(context,
        MaterialPageRoute(builder: (_) => const PinduoduoSyncScreen()));
    await _reloadParcels();                                // обновить список после синка
  } catch (_) {}
}
```

Экран «Синхронизация…» мелькнёт на пару секунд и закроется сам. На 1×1 спрятать
нельзя (PDD не грузит список), но можно прикрыть полупрозрачным оверлеем.

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

**Фильтр на сервере** (`_normalize_pdd_order`) — «чёрный список»: отбрасываются
ТОЛЬКО `交易已取消` (отменён), `待付款/待支付` (не оплачен), `退款` (возврат).
Всё остальное сохраняется: `待评价/交易成功` → `delivered` (получен),
`待收货/已发货/运输` или есть трек → `shipped` (в пути), прочее → `paid`.

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

1. Внедрить `PinduoduoSyncScreen` (§7) в боевой флоу — кнопка «Обновить заказы
   PDD». **Пересобрать приложение** (новый экран hot-reload-ом не подтянется).
   Поля заказа НЕ мапить — шлём сырой `data['orders']`, разбор на сервере.
2. Tab-клик (`_pddClickTabsJs`) должен быть именно в **боевом** sync-экране,
   который шлёт на `/ingest`, а не только в дебаг-экране. Иначе придут лишь
   заказы вкладки «全部» (часто одни отменённые → `created:0`).
3. Обработать «сессия истекла»: после `/session-expired/` придёт уведомление с
   `data.reason="session_expired"` → показать кнопку «Подключить заново».

---

## 11. Чеклист проверки

- [ ] Логин в WebView проходит (клиент видит свой кабинет PDD).
- [ ] После логина пришёл `POST /connect/` (status → `is_connected: true`).
- [ ] **Сессия переживает перезапуск приложения**: закрыть/открыть приложение →
      sync-экран НЕ редиректит на login (cookies восстановились из storage).
- [ ] Sync-экран **кликает вкладки** и ловит `order_list_v4` (handler `pddOrders`).
- [ ] `POST /ingest/` ушёл с **активными** заказами (не только отменёнными «全部»).
- [ ] `created > 0`, заказы появились в приложении (`/api/orders/`).
- [ ] У заказов с трек-номером появились посылки (`/api/parcels/`).
- [ ] Повторный синк не плодит дубли (`created: 0, updated: N`).
- [ ] При протухшей сессии летит `/session-expired/` и приходит уведомление.

---

## 12. Экран списка посылок (карточки)

`GET /api/parcels/` уже отдаёт по каждой посылке: `track_number`, `status`,
`status_display_name`, и из связанного заказа — `product_title`, `product_price`,
`product_image`. Рисуем карточки.

### Модель + репозиторий

```dart
class Parcel {
  final int id;
  final String trackNumber, status, statusName, title;
  final String? image;
  final num? price;
  Parcel({required this.id, required this.trackNumber, required this.status,
    required this.statusName, required this.title, this.image, this.price});

  factory Parcel.fromJson(Map<String, dynamic> j) => Parcel(
    id: j['id'],
    trackNumber: (j['track_number'] ?? '').toString(),
    status: (j['status'] ?? '').toString(),
    statusName: (j['status_display_name'] ?? '').toString(),
    title: (j['product_title'] ?? '').toString(),
    image: j['product_image'] as String?,
    price: j['product_price'] is String
        ? num.tryParse(j['product_price']) : j['product_price'] as num?,
  );
}

class ParcelRepository {
  final Dio dio; // с JWT
  ParcelRepository(this.dio);

  Future<List<Parcel>> list() async {
    final r = await dio.get('/api/parcels/');
    // DRF может отдавать список или {results:[...]} при пагинации.
    final data = r.data is Map ? (r.data['results'] ?? []) : r.data;
    return (data as List).map((e) => Parcel.fromJson(e)).toList();
  }
}
```

### Экран

```dart
class ParcelsScreen extends StatefulWidget {
  const ParcelsScreen({super.key});
  @override State<ParcelsScreen> createState() => _ParcelsScreenState();
}

class _ParcelsScreenState extends State<ParcelsScreen> {
  late Future<List<Parcel>> _future;

  @override
  void initState() {
    super.initState();
    _future = parcelRepository.list();
    // авто-синк PDD при заходе (см. §7 «Авто-запуск»)
    WidgetsBinding.instance.addPostFrameCallback((_) => _autoSyncPdd());
  }

  Future<void> _reload() async {
    final f = parcelRepository.list();
    setState(() => _future = f);
    await f;
  }

  Future<void> _autoSyncPdd() async {
    try {
      final st = await pinduoduoRepository.status();
      if (st['is_connected'] != true || !mounted) return;
      await Navigator.push(context,
          MaterialPageRoute(builder: (_) => const PinduoduoSyncScreen()));
      await _reload();
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Мои посылки'),
        actions: [IconButton(icon: const Icon(Icons.refresh), onPressed: _reload)],
      ),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: FutureBuilder<List<Parcel>>(
          future: _future,
          builder: (_, snap) {
            if (snap.connectionState == ConnectionState.waiting) {
              return const Center(child: CircularProgressIndicator());
            }
            final items = snap.data ?? const [];
            if (items.isEmpty) {
              return ListView(children: const [
                SizedBox(height: 120),
                Center(child: Text('Посылок пока нет')),
              ]);
            }
            return ListView.separated(
              padding: const EdgeInsets.all(12),
              itemCount: items.length,
              separatorBuilder: (_, __) => const SizedBox(height: 10),
              itemBuilder: (_, i) => _ParcelCard(items[i]),
            );
          },
        ),
      ),
    );
  }
}

class _ParcelCard extends StatelessWidget {
  final Parcel p;
  const _ParcelCard(this.p);

  @override
  Widget build(BuildContext context) {
    return Card(
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: const EdgeInsets.all(10),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: p.image != null
                ? Image.network(p.image!, width: 64, height: 64, fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => const _Ph())
                : const _Ph(),
          ),
          const SizedBox(width: 10),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(p.title.isEmpty ? p.trackNumber : p.title,
                maxLines: 2, overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 4),
            Text('Трек: ${p.trackNumber}',
                style: const TextStyle(fontSize: 12, color: Colors.grey)),
            const SizedBox(height: 6),
            Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
              Chip(label: Text(p.statusName, style: const TextStyle(fontSize: 11)),
                  visualDensity: VisualDensity.compact),
              if (p.price != null)
                Text('¥${p.price!.toStringAsFixed(2)}',
                    style: const TextStyle(fontWeight: FontWeight.bold)),
            ]),
          ])),
        ]),
      ),
    );
  }
}

class _Ph extends StatelessWidget {
  const _Ph();
  @override
  Widget build(BuildContext context) => Container(
    width: 64, height: 64, color: Colors.black12,
    child: const Icon(Icons.inventory_2_outlined, color: Colors.black38));
}
```

Карточка показывает: **фото товара, название, трек, статус, цену**. Pull-to-refresh
и кнопка обновления дёргают `/api/parcels/`; при заходе автоматически запускается
PDD-синк (если аккаунт привязан).
