"""Подобрать «ничьи» посылки, для которых заказ приехал позже скана.

Оператор на складе в Китае сканирует коробку раньше, чем заказ успевает прийти
с маркетплейса. На момент скана заказа нет, посылка остаётся ничьей
(``created_pending``), а когда заказ появляется — его синхронизация такую
посылку раньше обходила. На проде так накопилось несколько сотен посылок:
клиент их не видит в списке, по треку не находит и уведомлений о них не получает.

Присваиваем только посылки **без хозяина и без заказа**: перехват посылки чужого
клиента — худшее, что тут может случиться, поэтому такие не трогаем.

По умолчанию молча: это починка данных, а не движение коробки, и пачка
уведомлений разом читалась бы клиентами как сбой. Нужны уведомления — ``--notify``.
"""

from collections import Counter

from django.core.management.base import BaseCommand
from django.db.models import Q

from orders.models import Order
from parcels.models import Parcel
from parcels.services import adopt_pending_parcel


class Command(BaseCommand):
    help = "Привязать ничьи посылки к заказам с тем же трек-номером"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Записать изменения. Без флага — только показать план.",
        )
        parser.add_argument(
            "--notify",
            action="store_true",
            help="Отправить клиентам уведомления по текущему статусу посылки.",
        )

    def handle(self, *args, **options):
        pending = Parcel.objects.filter(
            user__isnull=True, order__isnull=True, is_archived=False
        ).exclude(Q(track_number="") | Q(track_number__isnull=True))

        # Заказ ищем по треку и только с владельцем: без клиента привязывать
        # не к кому.
        tracks = list(pending.values_list("track_number", flat=True))
        orders = {
            o.track_number: o
            for o in Order.objects.select_related("user")
            .filter(track_number__in=tracks, user__isnull=False)
            .order_by("id")
        }

        pairs = [(p, orders[p.track_number]) for p in pending if p.track_number in orders]

        if not pairs:
            self.stdout.write("Ничьих посылок с подходящим заказом нет.")
            return

        by_status = Counter(p.status for p, _ in pairs)

        if not options["apply"]:
            self.stdout.write(f"Найдено пар посылка-заказ: {len(pairs)}")
            self.stdout.write("По текущему статусу посылки:")
            for status, count in by_status.most_common():
                self.stdout.write(f"  {status:<26} {count}")
            self.stdout.write(
                self.style.WARNING(
                    "\nПредпросмотр. Для записи — с --apply "
                    "(добавьте --notify, если нужны уведомления)."
                )
            )
            return

        moved = 0
        for parcel, order in pairs:
            adopt_pending_parcel(parcel, order, notify=options["notify"])
            moved += 1

        suffix = "с уведомлениями" if options["notify"] else "без уведомлений"
        self.stdout.write(self.style.SUCCESS(f"Привязано {suffix}: {moved}."))
        left = Parcel.objects.filter(
            user__isnull=True, order__isnull=True, is_archived=False
        ).count()
        self.stdout.write(f"Осталось ничьих посылок (заказа для них нет): {left}")
