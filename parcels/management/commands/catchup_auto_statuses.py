"""Разовая подтяжка статусов после смены сроков авто-цепочки.

Когда меняются AUTO_STATUS_DELAYS или порядок AUTO_FLOW, накопленные посылки
разом «догоняют» новый маршрут. Это движение вызвано правкой настроек, а не
реальным перемещением коробок, поэтому уведомления гасятся: пуш «посылка в
пути» здесь был бы ложным, а при сотнях посылок ещё и выглядел бы сбоем.

Обычный крон (advance_parcels) уведомления шлёт — он реагирует на реальное
течение времени.
"""

from collections import Counter

from django.core.management.base import BaseCommand

from parcels.models import Parcel
from parcels.services import AUTO_FLOW, advance_all_parcels


class Command(BaseCommand):
    help = "Подтянуть статусы под новые сроки, не уведомляя клиентов"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Записать изменения. Без флага — только показать план.",
        )

    def handle(self, *args, **options):
        qs = Parcel.objects.filter(status__in=AUTO_FLOW[:-1], is_archived=False)

        if not options["apply"]:
            # План считаем без записи: прогоняем ту же логику на копиях.
            plan = Counter()
            for parcel in qs.iterator():
                target = _target_status(parcel)
                if target != parcel.status:
                    plan[(parcel.status, target)] += 1
            total = sum(plan.values())
            for (a, b), n in plan.most_common():
                self.stdout.write(f"  {a:<26} → {b:<26} {n}")
            self.stdout.write(
                self.style.WARNING(f"\nПредпросмотр: сдвинется {total}. Для записи — с --apply.")
            )
            return

        moved = advance_all_parcels(notify=False)
        self.stdout.write(self.style.SUCCESS(f"Подтянуто без уведомлений: {moved}."))
        left = Counter(
            Parcel.objects.filter(status__in=AUTO_FLOW, is_archived=False).values_list("status", flat=True)
        )
        for st, n in left.most_common():
            self.stdout.write(f"  {st:<26} {n}")


def _target_status(parcel):
    """Куда посылка уедет по текущим настройкам — без записи в БД."""
    from datetime import timedelta

    from django.conf import settings
    from django.utils import timezone

    from parcels.services import _auto_anchor

    if parcel.status not in AUTO_FLOW:
        return parcel.status
    idx = AUTO_FLOW.index(parcel.status)
    delays = settings.AUTO_STATUS_DELAYS
    threshold = _auto_anchor(parcel)
    now = timezone.now()
    target = idx
    for i in range(len(AUTO_FLOW) - 1):
        step = delays.get(AUTO_FLOW[i])
        if step is None:
            break
        threshold = threshold + timedelta(seconds=step)
        if threshold <= now:
            target = i + 1
        else:
            break
    return AUTO_FLOW[max(idx, target)]
