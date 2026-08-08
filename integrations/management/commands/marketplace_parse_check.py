"""Проверка разбора реального ответа маркетплейса — без записи в базу.

Маппинг полей Taobao/PDD написан по документированной структуре, а реальный
ответ может называть поля иначе. Команда показывает, что сервер извлёк бы из
конкретного ответа, чтобы поправить раскладку до первого настоящего синка.

    manage.py marketplace_parse_check --marketplace taobao --file orders.json
    cat orders.json | manage.py marketplace_parse_check --marketplace taobao

На вход принимается что угодно из перечисленного:
  * массив заказов;
  * полный ответ mtop/PDD — заказы находятся сами (data.orders, result и т.п.);
  * JSONP-обёртка ``mtopjsonp1({...})`` — скобки снимаются.
"""

import json
import re
import sys

from django.core.management.base import BaseCommand, CommandError

from integrations.marketplaces import MARKETPLACES, get_marketplace

# Где у ответов обычно лежит список заказов.
ORDER_LIST_KEYS = ("orders", "orderList", "list", "data", "result", "mainOrders")


def _strip_jsonp(text: str) -> str:
    """``mtopjsonp1({...})`` → ``{...}``. Обычный JSON не трогаем."""
    text = text.strip()
    match = re.match(r"^[A-Za-z_$][\w$]*\s*\((.*)\)\s*;?$", text, re.DOTALL)
    return match.group(1) if match else text


def _find_orders(node, depth=0):
    """Ищем в ответе список заказов: массив словарей с похожими ключами."""
    if depth > 6:
        return None
    if isinstance(node, list):
        if node and all(isinstance(item, dict) for item in node):
            return node
        return None
    if not isinstance(node, dict):
        return None
    # Сначала привычные имена, затем — обход всего дерева.
    for key in ORDER_LIST_KEYS:
        if key in node:
            found = _find_orders(node[key], depth + 1)
            if found:
                return found
    for value in node.values():
        found = _find_orders(value, depth + 1)
        if found:
            return found
    return None


class Command(BaseCommand):
    help = "Показать, как сервер разберёт реальный ответ маркетплейса (без записи)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--marketplace",
            required=True,
            help=f"Один из: {', '.join(MARKETPLACES)}",
        )
        parser.add_argument("--file", default="", help="Файл с JSON (по умолчанию stdin)")

    def handle(self, *args, **options):
        marketplace = get_marketplace(options["marketplace"])

        raw_text = (
            open(options["file"], encoding="utf-8").read()
            if options["file"]
            else sys.stdin.read()
        )
        if not raw_text.strip():
            raise CommandError("Пустой ввод: укажите --file или подайте JSON в stdin")
        try:
            payload = json.loads(_strip_jsonp(raw_text))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Не похоже на JSON: {exc}") from exc

        # Ответ без сессии приходит с кодом 200 и пустым data — по HTTP его не
        # отличить от нормального. Проверяем конверт mtop, иначе человек будет
        # думать, что сломался разбор, хотя на деле нужно просто перелогиниться.
        ret = payload.get("ret") if isinstance(payload, dict) else None
        if isinstance(ret, list) and ret:
            code = str(ret[0])
            if "SESSION_EXPIRED" in code or "NEED_LOGIN" in code:
                raise CommandError(
                    f"Это ответ без сессии: {code}. Залогиньтесь в Taobao и снимите "
                    "ответ заново — заказов в нём нет."
                )
            if not code.startswith("SUCCESS"):
                self.stdout.write(self.style.WARNING(f"Маркетплейс вернул: {code}"))

        # У маркетплейсов с деревом компонентов (Taobao) заказы собираются из
        # ответа целиком — обычный поиск списка тут не работает.
        orders = marketplace.extract(payload) if marketplace.extract else None
        if not orders:
            orders = _find_orders(payload)
        if orders is None:
            raise CommandError(
                "Не нашёл список заказов в ответе. Пришлите массив заказов "
                "или ответ целиком — тогда покажите верхние ключи: "
                f"{list(payload)[:10] if isinstance(payload, dict) else type(payload).__name__}"
            )

        self.stdout.write(f"Маркетплейс: {marketplace.title}")
        self.stdout.write(f"Найдено заказов в ответе: {len(orders)}\n")

        kept = skipped = unknown = 0
        gaps = []  # сохранённые заказы с пустыми полями — признак кривой раскладки
        for index, raw in enumerate(orders, 1):
            if not marketplace.is_raw(raw):
                unknown += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"{index}. НЕ ОПОЗНАН как сырой заказ — ключи: {sorted(raw)[:12]}"
                    )
                )
                continue
            parsed = marketplace.normalize(raw)
            if parsed is None:
                skipped += 1
                self.stdout.write(f"{index}. пропущен (отменён/не оплачен)")
                continue
            kept += 1
            missing = [
                name
                for name, value in (
                    ("товар", parsed["product_title"]),
                    ("сумма", parsed["price"]),
                )
                if not value
            ]
            if missing:
                gaps.append((parsed["external_order_id"], missing))
            self.stdout.write(
                self.style.SUCCESS(f"{index}. {parsed['external_order_id']}")
            )
            self.stdout.write(f"     товар:  {parsed['product_title'] or '— пусто —'}")
            self.stdout.write(f"     сумма:  {parsed['price'] if parsed['price'] is not None else '— пусто —'}")
            self.stdout.write(f"     кол-во: {parsed['quantity']}")
            self.stdout.write(f"     статус: {parsed['status']}")
            self.stdout.write(f"     трек:   {parsed['track_number'] or '—'}")

        self.stdout.write(
            f"\nИтог: сохранилось бы {kept}, отфильтровано {skipped}, не опознано {unknown}"
        )
        for order_id, missing in gaps:
            self.stdout.write(
                self.style.WARNING(f"  {order_id}: не заполнено — {', '.join(missing)}")
            )
        if unknown or gaps:
            self.stdout.write(
                self.style.WARNING(
                    "Раскладка полей не совпала с реальным ответом — пришлите этот "
                    "вывод и один сырой заказ, поправлю."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("Раскладка полей совпала полностью."))
