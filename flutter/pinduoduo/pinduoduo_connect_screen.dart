import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

import 'pdd_api.dart';
import 'pdd_session.dart';

/// Экран привязки Pinduoduo: клиент логинится сам (телефон + SMS).
/// Вход определяем по появлению cookie PDDAccessToken (НЕ по URL — иначе экран
/// закроется на промежуточной странице ввода кода).
class PinduoduoConnectScreen extends StatefulWidget {
  final PddApi api;
  const PinduoduoConnectScreen({super.key, required this.api});

  @override
  State<PinduoduoConnectScreen> createState() => _PinduoduoConnectScreenState();
}

class _PinduoduoConnectScreenState extends State<PinduoduoConnectScreen> {
  final _cookieManager = CookieManager.instance();
  InAppWebViewController? _controller;
  Timer? _poll;
  bool _connected = false;

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

  Future<bool> _isLoggedIn() async {
    if (_controller == null) return false;
    // iOS: обязательно webViewController, иначе getCookies вернёт [].
    final cookies = await _cookieManager.getCookies(
      url: WebUri('https://mobile.pinduoduo.com'),
      webViewController: _controller,
    );
    bool has(String n) =>
        cookies.any((c) => c.name == n && (c.value?.toString().isNotEmpty ?? false));
    return has('PDDAccessToken') || has('pdd_user_id');
  }

  Future<void> _finish() async {
    if (_connected || !mounted) return;
    _connected = true;
    _poll?.cancel();
    await PddSession.save(_controller);
    await widget.api.connect();
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
          // Фолбэк, если авто-детект не сработал, а клиент видит, что вошёл.
          TextButton(
            onPressed: _finish,
            child: const Text('Готово', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
      body: InAppWebView(
        initialUrlRequest:
            URLRequest(url: WebUri('https://mobile.pinduoduo.com/login.html')),
        onWebViewCreated: (c) => _controller = c,
        onLoadStop: (controller, url) => _checkLogin(),
        onUpdateVisitedHistory: (controller, url, isReload) => _checkLogin(),
      ),
    );
  }
}
