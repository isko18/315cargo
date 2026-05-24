from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from cargo.models import CargoCompany
from city_delivery.models import CityDeliveryTariff
from orders.models import Order
from parcels.models import Parcel
from pickup_points.models import PickupPoint
from shops.models import Shop

User = get_user_model()

DEFAULT_CARGO = {
    "title": "315CARGO",
    "slug": "315cargo",
    "description": "Демо карго-центр платформы",
    "phone": "+996700000000",
    "address": "Бишкек",
}

PICKUP_POINTS = [
    {
        "title": "ПВЗ Бишкек Центр",
        "address": "Бишкек, ул. Чуй 100",
        "phone": "+996700100100",
        "work_schedule": "Пн-Сб 09:00-19:00",
    },
    {
        "title": "ПВЗ Бишкек Восток",
        "address": "Бишкек, ул. Жибек Жолу 50",
        "phone": "+996700200200",
        "work_schedule": "Пн-Сб 09:00-19:00",
    },
    {
        "title": "ПВЗ Ош",
        "address": "Ош, ул. Курманжан Датка 12",
        "phone": "+996700300300",
        "work_schedule": "Пн-Вс 09:00-18:00",
    },
]

SHOPS = [
    {
        "title": "Pinduoduo",
        "slug": "pinduoduo",
        "url": "https://mobile.yangkeduo.com/",
        "client_code_strategy": Shop.ClientCodeStrategy.QUERY_PARAM,
        "query_param_name": "client_code",
        "sort_order": 1,
    },
    {
        "title": "Taobao",
        "slug": "taobao",
        "url": "https://m.taobao.com/",
        "client_code_strategy": Shop.ClientCodeStrategy.CLIPBOARD,
        "sort_order": 2,
    },
    {
        "title": "1688",
        "slug": "1688",
        "url": "https://m.1688.com/",
        "client_code_strategy": Shop.ClientCodeStrategy.MANUAL_INSTRUCTION,
        "sort_order": 3,
    },
    {
        "title": "Poizon",
        "slug": "poizon",
        "url": "https://www.dewu.com/",
        "client_code_strategy": Shop.ClientCodeStrategy.MANUAL_INSTRUCTION,
        "sort_order": 4,
    },
]

TARIFFS = [
    {
        "title": "Бишкек стандарт",
        "base_price": Decimal("150"),
        "price_per_kg": Decimal("30"),
        "free_weight_kg": Decimal("1"),
        "min_price": Decimal("150"),
        "is_default": True,
    },
    {
        "title": "Ош стандарт",
        "base_price": Decimal("200"),
        "price_per_kg": Decimal("50"),
        "free_weight_kg": Decimal("0"),
        "min_price": Decimal("200"),
        "is_default": False,
    },
]


class Command(BaseCommand):
    help = "Seed демонстрационные данные: карго, ПВЗ, магазины, тарифы и тестовый клиент"

    def add_arguments(self, parser):
        parser.add_argument(
            "--client-phone",
            default="+996700000001",
            help="Телефон демо-клиента, который будет создан",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Удалить существующие данные перед сидом",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            self.stdout.write("Очищаю демо-данные…")
            Parcel.objects.all().delete()
            Order.objects.all().delete()
            Shop.objects.all().delete()
            CityDeliveryTariff.objects.all().delete()
            PickupPoint.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()
            CargoCompany.objects.all().delete()

        cargo, _ = CargoCompany.objects.update_or_create(
            slug=DEFAULT_CARGO["slug"], defaults=DEFAULT_CARGO
        )
        self.stdout.write(self.style.SUCCESS(f"Карго-центр: {cargo.title}"))

        pickup_points = []
        for data in PICKUP_POINTS:
            pp, _ = PickupPoint.objects.update_or_create(
                cargo=cargo, title=data["title"], defaults=data
            )
            pickup_points.append(pp)
        self.stdout.write(self.style.SUCCESS(f"ПВЗ: {len(pickup_points)}"))

        for data in SHOPS:
            Shop.objects.update_or_create(cargo=cargo, slug=data["slug"], defaults=data)
        self.stdout.write(self.style.SUCCESS(f"Магазины: {len(SHOPS)}"))

        for index, data in enumerate(TARIFFS):
            defaults = {**data}
            if index < len(pickup_points):
                defaults["pickup_point"] = pickup_points[index]
            CityDeliveryTariff.objects.update_or_create(
                title=data["title"], defaults=defaults
            )
        self.stdout.write(self.style.SUCCESS(f"Тарифы: {len(TARIFFS)}"))

        phone = options["client_phone"]
        user, created = User.objects.get_or_create(
            phone=phone,
            cargo=cargo,
            defaults={"full_name": "Демо Клиент", "pickup_point": pickup_points[0]},
        )
        if created:
            user.set_unusable_password()
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Создан клиент {phone}"))
        else:
            self.stdout.write(f"Клиент {phone} уже существует")

        Order.objects.get_or_create(
            user=user,
            external_order_id="DEMO-1",
            defaults={
                "source": Order.Source.MANUAL,
                "product_title": "Демо-товар: куртка",
                "product_url": "https://example.com/jacket",
                "price": Decimal("1500.00"),
                "quantity": 1,
                "status": Order.Status.PAID,
            },
        )

        Parcel.objects.get_or_create(
            track_number="DEMO-TRACK-001",
            defaults={
                "user": user,
                "client_code": user.client_code or "",
                "status": Parcel.Status.ARRIVED_KYRGYZSTAN,
                "location": "Бишкек, склад",
                "weight": Decimal("2.5"),
                "delivery_price": Decimal("0"),
            },
        )

        self.stdout.write(self.style.SUCCESS("Готово."))
        self.stdout.write(
            f"Клиентский код демо-клиента: {User.objects.get(phone=phone, cargo=cargo).client_code}"
        )
