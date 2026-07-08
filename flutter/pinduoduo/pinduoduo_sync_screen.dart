import 'dart:async';
import 'dart:collection';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

import 'pdd_api.dart';
import 'pdd_js.dart';
import 'pdd_session.dart';

/// Синк-экран: грузит orders.html, САМ проходит вкладки + скроллит, перехватывает
/// order_list_v4 и шлёт сырые заказы на /ingest. Клиент ничего не нажимает.
///
/// ВАЖНО: WebView видимого размера (НЕ 1×1) — иначе PDD ленится грузить список.
class PinduoduoSyncScreen extends StatefulWidget {
  final PddApi api;
  const PinduoduoSyncScreen({super.key, required this.api});

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
    PddSession.restore().then((_) {
      if (mounted) setState(() => _ready = true);
    });
    _timeout = Timer(const Duration(seconds: 45), _finish);
  }

  @override
  void dispose() {
    _timeout?.cancel();
    super.dispose();
  }

  void _finish() {
    if (_done || !mounted) return;
    _done = true;
    _timeout?.cancel();
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
      final r = await widget.api.ingest(orders);
      _created += (r['created'] as int? ?? 0);
      await PddSession.save(_c);
      if (mounted) setState(() => _status = 'Сохранено новых: $_created');
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
        actions: [
          TextButton(
            onPressed: _finish,
            child: const Text('Готово', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
      body: InAppWebView(
        initialUrlRequest:
            URLRequest(url: WebUri('https://mobile.pinduoduo.com/orders.html')),
        initialUserScripts: UnmodifiableListView([
          UserScript(
            source: pddInterceptHookJs,
            injectionTime: UserScriptInjectionTime.AT_DOCUMENT_START,
          ),
        ]),
        onWebViewCreated: (c) {
          _c = c;
          c.addJavaScriptHandler(
            handlerName: 'pddOrders',
            callback: (a) => _onOrders(a.isNotEmpty ? a.first as String : ''),
          );
        },
        onLoadStop: (controller, url) async {
          final u = url?.toString() ?? '';
          if (u.contains('login.html') || u.contains('psnl_verification')) {
            await widget.api.markSessionExpired();
            _finish();
            return;
          }
          await PddSession.save(_c);
          await controller.evaluateJavascript(source: pddAutoSyncJs);
        },
      ),
    );
  }
}
