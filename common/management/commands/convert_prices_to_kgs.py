"""Разовый пересчёт денежных сумм из долларов в сомы.

Панель перешла на сом: тариф карго и стоимость посылок теперь считаются
в сомах. Старые значения были посчитаны в долларах, поэтому их надо умножить
на курс — одним проходом, вручную, с явным курсом.

    manage.py convert_prices_to_kgs --rate 87.5 --dry-run   # посмотреть
    manage.py convert_prices_to_kgs --rate 87.5             # применить

Команда не идемпотентна: повторный запуск умножит суммы ещё раз. Поэтому
сначала всегда --dry-run.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cargo.models import CargoCompany
from city_delivery.models import CityDeliveryTariff
from parcels.models import Parcel

CENT = Decimal("0.01")


def _mul(value, rate):
    if value is None:
        return None
    return (Decimal(value) * rate).quantize(CENT, rounding=ROUND_HALF_UP)


class Command(BaseCommand):
    help = "Пересчитать тарифы и стоимость посылок из USD в KGS по заданному курсу"

    def add_arguments(self, parser):
        parser.add_argument(
            "--rate",
            required=True,
            help="Курс: сколько сомов в одном долларе (напр. 87.5)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только показать, что изменится — ничего не записывать",
        )
        parser.add_argument(
            "--city-delivery",
            action="store_true",
            help="Пересчитать ещё и тарифы доставки по городу (если они были в $)",
        )

    def handle(self, *args, **options):
        try:
            rate = Decimal(str(options["rate"]))
        except Exception as exc:  # noqa: BLE001 — хотим внятную ошибку в CLI
            raise CommandError(f"Некорректный курс: {options['rate']}") from exc
        if rate <= 0:
            raise CommandError("Курс должен быть больше нуля")

        dry = options["dry_run"]
        self.stdout.write(f"Курс: 1 USD = {rate} KGS{'  (пробный прогон)' if dry else ''}")

        with transaction.atomic():
            # --- Тарифы карго ---
            cargos = list(CargoCompany.objects.order_by("id"))
            for c in cargos:
                old = c.price_per_kg_kgs
                new = _mul(old, rate)
                self.stdout.write(f"  карго #{c.id} {c.title}: {old} → {new}")
                c.price_per_kg_kgs = new
            if not dry and cargos:
                CargoCompany.objects.bulk_update(cargos, ["price_per_kg_kgs"])

            # --- Стоимость посылок ---
            parcels = list(Parcel.objects.exclude(delivery_price=None).only("id", "delivery_price"))
            for p in parcels:
                p.delivery_price = _mul(p.delivery_price, rate)
            if not dry and parcels:
                Parcel.objects.bulk_update(parcels, ["delivery_price"], batch_size=500)
            self.stdout.write(f"  посылок с ценой: {len(parcels)}")

            # --- Тарифы доставки по городу (опционально) ---
            city = []
            if options["city_delivery"]:
                city = list(CityDeliveryTariff.objects.order_by("id"))
                for t in city:
                    t.base_price = _mul(t.base_price, rate)
                    t.price_per_kg = _mul(t.price_per_kg, rate)
                    t.min_price = _mul(t.min_price, rate)
                if not dry and city:
                    CityDeliveryTariff.objects.bulk_update(
                        city, ["base_price", "price_per_kg", "min_price"]
                    )
                self.stdout.write(f"  тарифов доставки по городу: {len(city)}")

            if dry:
                transaction.set_rollback(True)

        if dry:
            self.stdout.write(self.style.WARNING("Пробный прогон — ничего не сохранено"))
        else:
            self.stdout.write(self.style.SUCCESS("Готово: суммы пересчитаны в сомы"))
