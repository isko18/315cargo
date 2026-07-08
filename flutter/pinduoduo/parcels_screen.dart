import 'package:flutter/material.dart';

import 'pdd_api.dart';
import 'pinduoduo_connect_screen.dart';
import 'pinduoduo_sync_screen.dart';

/// Экран «Мои посылки»: карточки с фото/названием/треком/статусом/ценой из
/// /api/parcels/. При заходе автоматически запускает PDD-синк (если привязан).
class ParcelsScreen extends StatefulWidget {
  final PddApi api;
  const ParcelsScreen({super.key, required this.api});

  @override
  State<ParcelsScreen> createState() => _ParcelsScreenState();
}

class _ParcelsScreenState extends State<ParcelsScreen> {
  late Future<List<Parcel>> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.api.parcels();
    WidgetsBinding.instance.addPostFrameCallback((_) => _autoSyncPdd());
  }

  Future<void> _reload() async {
    final f = widget.api.parcels();
    setState(() => _future = f);
    await f;
  }

  Future<void> _autoSyncPdd() async {
    if (!await widget.api.isConnected() || !mounted) return;
    await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => PinduoduoSyncScreen(api: widget.api)),
    );
    await _reload();
  }

  Future<void> _connectPdd() async {
    final ok = await Navigator.push<bool>(
      context,
      MaterialPageRoute(builder: (_) => PinduoduoConnectScreen(api: widget.api)),
    );
    if (ok == true) await _autoSyncPdd();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Мои посылки'),
        actions: [
          IconButton(icon: const Icon(Icons.link), tooltip: 'Подключить Pinduoduo', onPressed: _connectPdd),
          IconButton(icon: const Icon(Icons.refresh), tooltip: 'Обновить', onPressed: _reload),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _reload,
        child: FutureBuilder<List<Parcel>>(
          future: _future,
          builder: (_, snap) {
            if (snap.connectionState == ConnectionState.waiting) {
              return const Center(child: CircularProgressIndicator());
            }
            if (snap.hasError) {
              return ListView(children: [
                const SizedBox(height: 120),
                Center(child: Text('Ошибка загрузки: ${snap.error}')),
              ]);
            }
            final items = snap.data ?? const <Parcel>[];
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
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: p.image != null
                  ? Image.network(p.image!, width: 64, height: 64, fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => const _Ph())
                  : const _Ph(),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(p.title.isEmpty ? p.trackNumber : p.title,
                      maxLines: 2, overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontWeight: FontWeight.w600)),
                  const SizedBox(height: 4),
                  Text('Трек: ${p.trackNumber}',
                      style: const TextStyle(fontSize: 12, color: Colors.grey)),
                  const SizedBox(height: 6),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Chip(
                        label: Text(p.statusName, style: const TextStyle(fontSize: 11)),
                        visualDensity: VisualDensity.compact,
                        materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                      if (p.price != null)
                        Text('¥${p.price!.toStringAsFixed(2)}',
                            style: const TextStyle(fontWeight: FontWeight.bold)),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Ph extends StatelessWidget {
  const _Ph();
  @override
  Widget build(BuildContext context) => Container(
        width: 64,
        height: 64,
        color: Colors.black12,
        child: const Icon(Icons.inventory_2_outlined, color: Colors.black38),
      );
}
