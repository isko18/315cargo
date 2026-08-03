import time

from django.core.management.base import BaseCommand

from parcels.services import advance_all_parcels


class Command(BaseCommand):
    help = (
        "Двигает посылки по авто-цепочке статусов (после 1-го скана на складе "
        "в Китае и до 2-го скана в ПВЗ).\n"
        "Прод: запускается Celery beat каждые 5 мин. Локально без Celery можно "
        "гонять в цикле: python manage.py advance_parcels --loop"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Запускать в бесконечном цикле (для локальной разработки без Celery).",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=60,
            help="Интервал цикла в секундах (по умолчанию 60).",
        )

    def handle(self, *args, **options):
        if options["loop"]:
            interval = max(5, options["interval"])
            self.stdout.write(
                self.style.WARNING(f"Цикл продвижения статусов каждые {interval}с. Ctrl+C для выхода.")
            )
            try:
                while True:
                    moved = advance_all_parcels()
                    if moved:
                        self.stdout.write(self.style.SUCCESS(f"Продвинуто посылок: {moved}"))
                    time.sleep(interval)
            except KeyboardInterrupt:
                self.stdout.write("Остановлено.")
            return

        moved = advance_all_parcels()
        self.stdout.write(self.style.SUCCESS(f"Продвинуто посылок: {moved}"))
