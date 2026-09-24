"""Разовый увод посылок из статуса «Классификация и обработка».

Этот статус убран из AUTO_FLOW: маршрут стал «склад в Китае → В пути →
На таможне». Посылки, застрявшие в обработке на момент смены, больше никто не
двигает — авто-цепочка пропускает всё, чего нет во flow. Команда переводит их
в «В пути», то есть в тот шаг, на который они и попали бы по новому маршруту.

Уведомления гасятся: сдвиг вызван правкой маршрута, а не движением коробки,
и пуш «посылка в пути» здесь был бы ложным.

Команда идемпотентна — повторный запуск просто не найдёт кандидатов.
"""

from django.core.management.base import BaseCommand

from parcels.models import Parcel
from parcels.services import update_parcel_status


class Command(BaseCommand):
    help = "Перевести зависшие в «обработке» посылки в «В пути», не уведомляя клиентов"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Записать изменения. Без флага — только показать план.",
        )

    def handle(self, *args, **options):
        qs = Parcel.objects.filter(
            status=Parcel.Status.PROCESSING, is_archived=False
        ).order_by("id")
        total = qs.count()

        if not total:
            self.stdout.write("В «обработке» посылок нет — переводить нечего.")
            return

        if not options["apply"]:
            # Без стрелки-юникода: команду запускают и из Windows-консоли,
            # где cp1251 роняет вывод на таком символе.
            self.stdout.write(
                f"  {Parcel.Status.PROCESSING} -> {Parcel.Status.IN_TRANSIT}: {total}"
            )
            self.stdout.write(
                self.style.WARNING(
                    f"\nПредпросмотр: сдвинется {total}. Для записи — с --apply."
                )
            )
            return

        moved = 0
        for parcel in qs.iterator():
            # Гасим пуш так же, как это делает подтяжка после смены сроков.
            parcel._suppress_notification = True
            update_parcel_status(
                parcel,
                Parcel.Status.IN_TRANSIT,
                comment="Маршрут изменён: обработка убрана из авто-цепочки",
            )
            moved += 1

        self.stdout.write(
            self.style.SUCCESS(f"Переведено в «В пути» без уведомлений: {moved}.")
        )
