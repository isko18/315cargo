from django.core.management.base import BaseCommand, CommandError

from cargo.models import CargoCompany
from city_delivery.models import CityDeliveryPoint

# Точки, которые дало карго и которые до справочника были зашиты в приложении.
POINTS = (
    "Круговой Ак-Тилек, чайхана Ала-Тоо",
    "Мост Учар, остановка Латибджанова",
    "Анар, круговой Миллион",
    "Жаны базар",
    "Центральная мечеть, Зайнабидинова",
    "ХБК / 122, конечная",
)


class Command(BaseCommand):
    help = "Завести карго шесть точек доставки по городу. Повторный запуск ничего не дублирует."

    def add_arguments(self, parser):
        parser.add_argument("--cargo", type=int, required=True, help="ID карго-центра")

    def handle(self, *args, **options):
        cargo = CargoCompany.objects.filter(pk=options["cargo"]).first()
        if cargo is None:
            raise CommandError(f"Карго {options['cargo']} не найдено")
        created = 0
        for position, title in enumerate(POINTS, start=1):
            _, is_new = CityDeliveryPoint.objects.get_or_create(
                cargo=cargo, title=title, defaults={"position": position}
            )
            created += is_new
        self.stdout.write(f"{cargo.title}: заведено {created}, уже были {len(POINTS) - created}")
