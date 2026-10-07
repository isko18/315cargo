"""Разовая починка заказов, у которых осталась заглушка рядом с реальной посылкой.

Заглушка — посылка с номером заказа вместо трека: синхронизация заводит её,
пока трека ещё нет. Подбор ничьих посылок 01.10 не учитывал заглушки и
привязывал к заказу ещё и реальную коробку — у 10 заказов на проде стало по
две посылки. Клиент видит обе в ПВЗ, выдают одну, по второй идут напоминания.

Здесь заглушка уступает место реальной посылке: отменяется молча и уходит в
архив. Трогаем только однозначные случаи — у заказа ровно одна посылка с
настоящим треком, а остальные заглушки, и ни одну из них не выдали.
Две посылки с настоящими треками — это две коробки, их не трогаем.
"""

from django.core.management.base import BaseCommand
from django.db.models import Count

from parcels.models import Parcel
from parcels.services import _is_placeholder, retire_placeholder


class Command(BaseCommand):
    help = "Убрать заглушки у заказов, где уже есть реальная посылка"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Записать изменения. Без флага — только показать план.",
        )

    def handle(self, *args, **options):
        order_ids = list(
            Parcel.objects.filter(order__isnull=False, is_archived=False)
            .exclude(status=Parcel.Status.CANCELLED)
            .values("order_id")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
            .values_list("order_id", flat=True)
        )

        fixable = []
        skipped = []
        for order_id in order_ids:
            parcels = list(
                Parcel.objects.select_related("order")
                .filter(order_id=order_id, is_archived=False)
                .exclude(status=Parcel.Status.CANCELLED)
            )
            order = parcels[0].order
            placeholders = [p for p in parcels if _is_placeholder(p, order)]
            real = [p for p in parcels if not _is_placeholder(p, order)]
            issued = any(p.status == Parcel.Status.ISSUED for p in placeholders)
            if len(real) == 1 and placeholders and not issued:
                fixable.append((real[0], placeholders))
            else:
                skipped.append(order_id)

        if not fixable and not skipped:
            self.stdout.write("Заказов с несколькими посылками нет.")
            return

        for real, placeholders in fixable:
            tracks = ", ".join(p.track_number for p in placeholders)
            self.stdout.write(f"  заказ {real.order_id}: оставить {real.track_number}, убрать {tracks}")
        if skipped:
            self.stdout.write(
                self.style.WARNING(
                    f"Не трогаем {len(skipped)} заказ(ов): там несколько настоящих "
                    f"треков или заглушку уже выдали — нужна ручная проверка. "
                    f"id: {', '.join(map(str, skipped))}"
                )
            )

        if not options["apply"]:
            self.stdout.write(
                self.style.WARNING(
                    f"\nПредпросмотр: исправится {len(fixable)}. Для записи — с --apply."
                )
            )
            return

        retired = 0
        for real, placeholders in fixable:
            for placeholder in placeholders:
                retire_placeholder(placeholder, replaced_by=real)
                retired += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Исправлено заказов: {len(fixable)}, убрано заглушек: {retired}."
            )
        )
