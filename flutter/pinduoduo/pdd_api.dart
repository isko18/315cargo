import 'package:dio/dio.dart';

/// Все обращения к бэкенду 315CARGO по Pinduoduo + посылкам.
/// Передай сюда свой Dio (с JWT-интерсептором и baseUrl).
class PddApi {
  final Dio dio;
  PddApi(this.dio);

  Future<void> connect() => dio.post(
        '/api/integrations/pinduoduo/connect/',
        data: {'session_data': {}},
      );

  /// Отправить СЫРЫЕ заказы из order_list_v4. Возвращает {synced, created, updated, errors}.
  Future<Map<String, dynamic>> ingest(List<Map<String, dynamic>> orders) async {
    final r = await dio.post(
      '/api/integrations/pinduoduo/ingest/',
      data: {'orders': orders},
    );
    return Map<String, dynamic>.from(r.data as Map);
  }

  Future<void> markSessionExpired() =>
      dio.post('/api/integrations/pinduoduo/session-expired/');

  Future<Map<String, dynamic>> status() async {
    final r = await dio.get('/api/integrations/pinduoduo/status/');
    return Map<String, dynamic>.from(r.data as Map);
  }

  Future<bool> isConnected() async {
    try {
      return (await status())['is_connected'] == true;
    } catch (_) {
      return false;
    }
  }

  /// Список посылок клиента (с данными товара из заказа PDD).
  Future<List<Parcel>> parcels() async {
    final r = await dio.get('/api/parcels/');
    final data = r.data is Map ? (r.data['results'] ?? const []) : r.data;
    return (data as List)
        .map((e) => Parcel.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList();
  }
}

class Parcel {
  final int id;
  final String trackNumber;
  final String status;
  final String statusName;
  final String title;
  final String? image;
  final num? price;

  Parcel({
    required this.id,
    required this.trackNumber,
    required this.status,
    required this.statusName,
    required this.title,
    this.image,
    this.price,
  });

  factory Parcel.fromJson(Map<String, dynamic> j) {
    final rawPrice = j['product_price'];
    return Parcel(
      id: j['id'] as int,
      trackNumber: (j['track_number'] ?? '').toString(),
      status: (j['status'] ?? '').toString(),
      statusName: (j['status_display_name'] ?? '').toString(),
      title: (j['product_title'] ?? '').toString(),
      image: j['product_image'] as String?,
      price: rawPrice is String ? num.tryParse(rawPrice) : rawPrice as num?,
    );
  }
}
