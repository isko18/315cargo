from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from cargo.models import CargoCompany
from orders.models import Order
from parcels.models import Parcel
from pickup_points.models import PickupPoint
from users.services import generate_client_code

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Создать/обновить тестового пользователя-ревьюера (для Google/Apple) "
        "с демо-заказами и посылками. Идемпотентно."
    )

    def add_arguments(self, parser):
        parser.add_argument("--phone", default="+996700000000")
        parser.add_argument("--name", default="Тестовый Ревьюер")
        parser.add_argument(
            "--cargo", default=None, help="ID или slug карго (по умолчанию первый активный)"
        )

    def handle(self, *args, **opts):
        phone = opts["phone"]
        raw_cargo = opts["cargo"]
        if raw_cargo:
            cargo = (
                (CargoCompany.objects.filter(pk=raw_cargo).first() if str(raw_cargo).isdigit() else None)
                or CargoCompany.objects.filter(slug=raw_cargo).first()
            )
        else:
            cargo = CargoCompany.objects.filter(is_active=True).first()
        if not cargo:
            raise CommandError("Нет карго-центра. Создай карго или запусти seed_demo.")

        pickup = PickupPoint.objects.filter(cargo=cargo, is_active=True).first()

        user = User.objects.filter(phone=phone, cargo=cargo).first()
        if user is None:
            user = User(phone=phone, cargo=cargo)
            user.set_unusable_password()
        user.full_name = opts["name"]
        user.is_active = True
        if not user.client_code:
            user.client_code = generate_client_code(cargo)
        if pickup:
            user.pickup_point = pickup
        user.save()

        orders = [
            ("REV-ORD-1", "Куртка зимняя", "150.00", Order.Status.PURCHASED, "REV-TRACK-1"),
            ("REV-ORD-2", "Кроссовки беговые", "80.00", Order.Status.ARRIVED_CHINA_WAREHOUSE, "REV-TRACK-2"),
            ("REV-ORD-3", "Наушники", "25.00", Order.Status.CREATED, ""),
        ]
        for ext, title, price, st, track in orders:
            Order.objects.update_or_create(
                user=user,
                source=Order.Source.PINDUODUO,
                external_order_id=ext,
                defaults=dict(
                    product_title=title, price=price, quantity=1, status=st, track_number=track
                ),
            )

        parcels = [
            ("REV-TRACK-1", Parcel.Status.SENT_TO_KYRGYZSTAN),
            ("REV-TRACK-2", Parcel.Status.ARRIVED_CHINA_WAREHOUSE),
            ("REV-TRACK-3", Parcel.Status.AT_PICKUP_POINT),
        ]
        for track, st in parcels:
            Parcel.objects.update_or_create(
                track_number=track,
                defaults=dict(
                    cargo=cargo, user=user, client_code=user.client_code, status=st
                ),
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Ревьюер готов: phone={phone}, cargo_id={cargo.id}, "
                f"client_code={user.client_code}. Код входа (whitelist OTP): см. OTP_TEST_NUMBERS."
            )
        )
