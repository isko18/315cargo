import 'dart:convert';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Сохранение/восстановление cookies сессии PDD.
///
/// `PDDAccessToken` обычно session-cookie без срока — не переживает перезапуск и
/// не всегда виден новому WebView-инстансу. Поэтому после логина сохраняем
/// cookies в secure storage и восстанавливаем перед orders.html, проставляя срок
/// (превращаем session-cookie в постоянный).
class PddSession {
  static const _key = 'pdd_cookies';
  static const _storage = FlutterSecureStorage();
  static final _cm = CookieManager.instance();
  static final _url = WebUri('https://mobile.pinduoduo.com');

  /// Вызывать после логина и после каждого синка.
  /// На iOS обязателен controller, иначе getCookies вернёт [].
  static Future<void> save([InAppWebViewController? controller]) async {
    final cookies = await _cm.getCookies(url: _url, webViewController: controller);
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

  /// Восстановить cookies перед загрузкой orders.html. false — если сессии нет.
  static Future<bool> restore() async {
    final raw = await _storage.read(key: _key);
    if (raw == null) return false;
    final list = jsonDecode(raw) as List;
    final expires =
        DateTime.now().add(const Duration(days: 30)).millisecondsSinceEpoch;
    for (final c in list) {
      final m = Map<String, dynamic>.from(c as Map);
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
    await _cm.flush();
    return list.isNotEmpty;
  }

  /// Полный сброс (при «отключить Pinduoduo» / протухшей сессии).
  static Future<void> clear() async {
    await _storage.delete(key: _key);
    await _cm.deleteCookies(url: _url);
  }
}
