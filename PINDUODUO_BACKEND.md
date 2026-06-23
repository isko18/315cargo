# Pinduoduo — что реализовано (бэкенд)

Сводка по интеграции парсинга заказов Pinduoduo и сопутствующим правкам.
Сторона Flutter описана отдельно в [FLUTTER_PINDUODUO.md](FLUTTER_PINDUODUO.md).

---

## 1. Архитектура (path B — перехват в WebView)

У PDD нет публичного API для покупателя; запросы защищены анти-ботом
(`anti-content`/`c-kf`/`verifyauthtoken` + проверка TLS). Проверено эмпирически:
сервер сам тянуть заказы **не может** (`SUSPECT`/`424`, подпись без браузера не
сгенерировать — открытые генераторы устарели).

Рабочая схема:
```
Клиент логинится в in-app WebView (1 раз)
  → JS-hook перехватывает ОТВЕТ order_list_v4 (его подписывает сама страница PDD)
  → приложение шлёт массив заказов на POST /api/integrations/pinduoduo/ingest/
бэкенд: разбор → фильтр → дедуп → Order + Parcel
```

**Ограничение (PDD):** одна активная сессия на аккаунт — логин в нашем WebView
выкидывает официальное приложение PDD, и наоборот. Постоянный фоновый sync
вызывает «пинг-понг» сессий; долгосрочно стоит рассмотреть «синк по требованию».

---

## 2. Эндпоинты

Все под JWT, работают от имени текущего клиента (`integrations/pinduoduo/views.py`):

| Метод | URL | Назначение |
|---|---|---|
| POST | `/api/integrations/pinduoduo/connect/` | пометить аккаунт подключённым |
| POST | `/api/integrations/pinduoduo/ingest/` | принять заказы из WebView |
| POST | `/api/integrations/pinduoduo/session-expired/` | сессия истекла → уведомить клиента |
| GET | `/api/integrations/pinduoduo/status/` | статус подключения |
| POST | `/api/integrations/pinduoduo/sync/` | pull через `PINDUODUO_CLIENT_PATH` (если задан) |
| POST | `/api/integrations/pinduoduo/webhook/` | приём от внешнего воркера (admin) |

Тело `/ingest/`: `{"orders": [ <сырые объекты order_list_v4> ]}`.
Ответ: `{synced, created, updated, errors}`.

---

## 3. Разбор заказа на сервере (`PinduoduoSyncService`)

`integrations/pinduoduo/services.py`:

- **`_normalize_pdd_order(raw)`** — сырой заказ PDD → нормализованный payload:
  - `external_order_id` = `order_sn`;
  - `product_title` = имена всех `order_goods[].goods_name` через ` | `;
  - `quantity` = сумма `goods_number`;
  - `price` = `order_amount / 100` (PDD хранит в фэнях: `98 → 0.98`);
  - `track_number` = `tracking_number`;
  - `raw` = весь объект (→ `Order.raw_data`).
- **Фильтр по `order_status_prompt`** — «чёрный список»: отбрасываем ТОЛЬКО
  отменённые/неоплаченные/возврат, **всё остальное сохраняем** (чтобы 待发货 не
  терялся из-за непривычной формулировки текста):
  - **отбрасываются**: 取消 (отменён), 待付款/待支付 (не оплачен), 退款/已退款 (возврат);
  - 交易成功/已完成/已收货/已签收 → `delivered` → `ARRIVED_CHINA_WAREHOUSE` (получен);
  - 待收货/已发货/运输/已送达 или есть трек → `shipped` → `PURCHASED` (в пути);
  - **всё прочее активное** (ждёт отправки, любая формулировка) → `paid`.
- **`_apply_order`** — берёт сырой заказ либо из корня payload (`order_sn`), либо
  из вложенного `payload["raw"]` (совместимость со старым приложением), нормализует,
  и `update_or_create` по `(user, source, external_order_id)`.
- **`ingest_orders`** — обёртка для эндпоинта `/ingest/` (атомарно, уведомление о
  новых заказах). `sync_orders` и `ingest_webhook_payload` используют тот же `_apply_order`.

---

## 4. Заказ = посылка (`_sync_parcel_for_order`)

На каждый сохранённый заказ создаётся `Parcel` (одна на заказ):
- идентификатор посылки — реальный `tracking_number`;
- пока трека нет (ждёт отправки) — временно `order_sn`;
- когда придёт реальный трек — он **заменяет** временный в той же посылке;
- чужие посылки не трогаются (guard по владельцу);
- проставляются `user`, `cargo`, `client_code`.

---

## 5. Карточка посылки: фото / название / цена

Данные товара берутся из связанного заказа:
- **API** (`parcels/serializers.py` → `ParcelSerializer`): добавлены
  `product_title`, `product_price`, `product_image`
  (`order.raw_data.order_goods[0].thumb_url`).
- **Админка** (`parcels/admin.py`): колонки **Фото** (превью) и **Товар**.

---

## 6. Дедуп заказов

`orders/models.py`: `UniqueConstraint(user, source, external_order_id)`
(partial — пустой `external_order_id` у ручных заказов не конфликтует).
Повторный синк не плодит дубли. Webhook-ингест обёрнут в `transaction.atomic`
с защитой от битых элементов.

---

## 7. Уведомления

- при новых заказах — push/in-app `PINDUODUO_SYNCED`;
- `session-expired` → `is_connected=False` + уведомление «войдите в PDD заново»
  (`data.reason="session_expired"`).

---

## 8. Тесты

`tests/test_pinduoduo.py` (всего по проекту 95 проходят):
- `test_ingest_raw_pdd_filters_and_parses` — фильтр отменённых, цена `/100`,
  статусы, посылка по треку и по `order_sn`;
- `test_ingest_normalized_with_raw_is_filtered` — разбор из `raw` (старое
  приложение), статус «получен», отмена отфильтрована;
- `test_ingest_creates_orders_and_parcels`, `test_ingest_dedup_and_parcel_owner_guard`,
  `test_session_expired_marks_account_and_notifies`, webhook-тесты.

---

## 9. Деплой и чистка

```bash
git pull origin master
# почистить мусор (отменённые, что налезли раньше):
python manage.py shell -c "from orders.models import Order; from parcels.models import Parcel; print(Parcel.objects.filter(order__source='pinduoduo').delete()); print(Order.objects.filter(source='pinduoduo').delete())"
systemctl restart gunicorn   # миграции PDD-логики не требуют
```
> Если pull ругается на untracked-миграцию (`notifications/0003_...`) — убрать её
> (`mv ... /tmp`) и повторить pull; файл из master тот же.

---

## 10. Сопутствующие правки безопасности/логики (ранее в этой сессии)

- cross-tenant `client_code`: импорт CSV и webhook скоупятся по карго; защита от
  подмены владельца посылки;
- OTP привязан к карго + лимит попыток (анти-брутфорс);
- реальная ротация/блэклист JWT refresh;
- Profile PATCH запрещает `pickup_point` из чужого карго;
- изоляция тарифов city-delivery по карго;
- простановка `arrived_at`/`issued_at` у посылок;
- уведомления уважают категорийные настройки; живой `marketing_enabled`.
