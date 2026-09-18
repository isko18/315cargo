"""Песочница для мобильной команды: карго, ПВЗ, оператор и демо-посылки.

Отдельное карго, а не аккаунт в боевом: тестовые сканы пишутся в общую
историю операций и уходят пушами живым клиентам, а отменить отправленный
push нельзя. Ценой пустой панели мы получаем песочницу, в которой не жалко
ничего сломать, — поэтому команда сразу засевает ПВЗ, клиентов и посылки
в разных статусах.

Карго заводится неактивным: список карго для клиентов отдаёт только
активные, так что в приложении песочница не появится.

    manage.py create_test_cargo                    # создать/обновить
    manage.py create_test_cargo --password 'секрет'
    manage.py create_test_cargo --dry-run

Команда идемпотентна: повторный запуск ничего не дублирует, а пароль
перевыставляет — им же её и используют для сброса.
"""

import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from cargo.models import CargoCompany
from parcels.models import Parcel
from pickup_points.models import PickupPoint
from users.services import generate_client_code

User = get_user_model()

CARGO_SLUG = "test-cargo"
STAFF_PHONE = "+996999000315"

# Два пункта, а не один: половина ошибок скоупа видна только когда есть
# второй ПВЗ, в который оператор не должен попадать.
POINTS = (
    ("Тест ПВЗ Бишкек", "Бишкек, тестовый адрес 1", "TSTB"),
    ("Тест ПВЗ Ош", "Ош, тестовый адрес 2", "TSTO"),
)

# Посылки в разных точках маршрута: приём, дорога, готова к выдаче, выдана.
DEMO_PARCELS = (
    ("TESTC-1", Parcel.Status.ARRIVED_CHINA_WAREHOUSE, False),
    ("TESTC-2", Parcel.Status.IN_TRANSIT, False),
    ("TESTC-3", Parcel.Status.AT_PICKUP_POINT, True),
    ("TESTC-4", Parcel.Status.ISSUED, True),
)


class Command(BaseCommand):
    help = "Создать/обновить тестовое карго с оператором и демо-данными (идемпотентно)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default=None,
            help="Пароль оператора. Без него генерируется и печатается один раз.",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Показать, что будет сделано, и выйти"
        )

    def handle(self, *args, **options):
        password = options["password"] or secrets.token_urlsafe(12)

        if options["dry_run"]:
            self.stdout.write(f"карго: {CARGO_SLUG} (неактивное)")
            for title, address, prefix in POINTS:
                self.stdout.write(f"  ПВЗ: {title} · {address} · коды {prefix}0001…")
            self.stdout.write(f"  оператор: {STAFF_PHONE} (админ карго)")
            self.stdout.write(f"  посылки: {', '.join(t for t, _s, _p in DEMO_PARCELS)}")
            self.stdout.write("\n--dry-run: ничего не записано.")
            return

        with transaction.atomic():
            cargo = self._cargo()
            points = [self._point(cargo, *row) for row in POINTS]
            staff = self._staff(cargo, points[0], password)
            clients = [self._client(cargo, point, index) for index, point in enumerate(points)]
            self._parcels(cargo, clients[0], points[0])

        self.stdout.write(self.style.SUCCESS(f"Карго #{cargo.id} «{cargo.title}» готово."))
        for point in points:
            self.stdout.write(f"  ПВЗ #{point.id} {point.title}")
        for client in clients:
            self.stdout.write(f"  клиент {client.phone} · код {client.client_code}")
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Вход в панель (POST /api/auth/token/):"))
        self.stdout.write(f"  login:    {staff.phone}")
        self.stdout.write(f"  password: {password}")
        if not options["password"]:
            self.stdout.write(
                self.style.WARNING("Пароль сгенерирован и больше нигде не хранится — сохраните.")
            )

    def _cargo(self):
        cargo, _ = CargoCompany.objects.update_or_create(
            slug=CARGO_SLUG,
            defaults=dict(
                title="Тестовое карго",
                code="TST",
                description="Песочница для мобильной команды. Не боевые данные.",
                # Неактивное: список карго для клиентов отдаёт только активные.
                is_active=False,
                price_per_kg_kgs=100,
                client_code_prefix="TST",
            ),
        )
        return cargo

    def _point(self, cargo, title, address, prefix):
        point, _ = PickupPoint.objects.update_or_create(
            cargo=cargo,
            title=title,
            defaults=dict(
                address=address,
                work_schedule="Пн-Вс 09:00–20:00",
                client_code_prefix=prefix,
                is_active=True,
            ),
        )
        return point

    def _staff(self, cargo, point, password):
        staff = User.objects.filter(phone=STAFF_PHONE, cargo=cargo).first()
        if staff is None:
            staff = User(phone=STAFF_PHONE, cargo=cargo)
        staff.full_name = "Тестовый оператор"
        staff.cargo = cargo
        # Админ карго, а не оператор ПВЗ: мобильной панели нужны все вкладки,
        # включая те, что привязанному оператору не видны.
        staff.is_staff = True
        staff.is_cargo_admin = True
        staff.is_active = True
        staff.pickup_point = None
        staff.set_password(password)
        staff.save()
        return staff

    def _client(self, cargo, point, index):
        phone = f"+9969990003{16 + index:02d}"
        client = User.objects.filter(phone=phone, cargo=cargo).first()
        if client is None:
            client = User(phone=phone, cargo=cargo, pickup_point=point)
            client.set_unusable_password()
        client.full_name = f"Тестовый клиент {index + 1}"
        client.cargo = cargo
        client.pickup_point = point
        client.is_active = True
        if not client.client_code:
            client.client_code = generate_client_code(cargo, point)
        client.save()
        return client

    def _parcels(self, cargo, client, point):
        for track, status, at_point in DEMO_PARCELS:
            Parcel.objects.update_or_create(
                track_number=track,
                defaults=dict(
                    cargo=cargo,
                    user=client,
                    client_code=client.client_code,
                    status=status,
                    pickup_point=point if at_point else None,
                    weight="2.000",
                ),
            )
