"""Тестовый клиент в каждом пункте выдачи — чтобы приём и выдачу можно было
проверить в любом ПВЗ, а не только в том, к которому привязан ревьюер.

Клиент по модели привязан ровно к одному ПВЗ (и живёт внутри одного карго),
поэтому «тестовый аккаунт во всех ПВЗ» — это по аккаунту на пункт. Номер
выводится из id пункта: ``+996700<id:06d>``, код входа у всех один. Оператор,
привязанный к своему ПВЗ, найдёт в поиске ровно «своего» тестового клиента.

    manage.py create_test_clients                # создать/обновить, показать номера
    manage.py create_test_clients --dry-run      # только показать, ничего не менять

Исторический номер ревьюера магазинов (``+996700000000``) команда не трогает.

После создания номера нужно внести в ``OTP_TEST_NUMBERS`` — иначе вход попросит
настоящую SMS. Готовая строка для ``.env`` печатается в конце.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from parcels.models import Parcel
from pickup_points.models import PickupPoint
from users.services import generate_client_code

User = get_user_model()

# Номер ревьюера магазинов: заведён вручную, со своими демо-данными.
LEGACY_REVIEWER_PHONE = "+996700000000"


def test_phone_for(pickup):
    """ПВЗ → тестовый номер. Стабильный: пересоздание не плодит аккаунты."""
    return f"+996700{pickup.id:06d}"


class Command(BaseCommand):
    help = "Создать/обновить тестового клиента в каждом активном ПВЗ (идемпотентно)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--code", default="0000", help="Код входа для тестовых номеров (по умолчанию 0000)"
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Показать, что будет сделано, и выйти"
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        pickups = list(
            PickupPoint.objects.filter(is_active=True)
            .select_related("cargo")
            .order_by("cargo_id", "id")
        )
        if not pickups:
            self.stdout.write(self.style.WARNING("Активных ПВЗ нет — нечего заводить."))
            return

        phones = []
        for pickup in pickups:
            phone = test_phone_for(pickup)
            phones.append(phone)
            label = f"{pickup.title} · {pickup.cargo.title}"
            if dry_run:
                self.stdout.write(f"{phone}  ←  ПВЗ #{pickup.id} {label}")
                continue

            user = User.objects.filter(
                phone=phone, is_staff=False, is_superuser=False
            ).order_by("id").first()
            created = user is None
            if created:
                user = User(phone=phone)
                user.set_unusable_password()
            user.cargo = pickup.cargo
            user.pickup_point = pickup
            user.full_name = f"Тест ПВЗ {pickup.title}"
            user.is_active = True
            if not user.client_code:
                user.client_code = generate_client_code(pickup.cargo)
            user.save()

            self._demo_parcels(user, pickup)
            mark = "создан" if created else "обновлён"
            self.stdout.write(
                self.style.SUCCESS(
                    f"{phone}  {mark}: {user.full_name} · код {user.client_code} · ПВЗ #{pickup.id} {label}"
                )
            )

        if dry_run:
            self.stdout.write("\n--dry-run: ничего не записано.")

        env_value = ",".join(
            f"{phone}:{options['code']}"
            for phone in [LEGACY_REVIEWER_PHONE, *phones]
        )
        self.stdout.write(
            "\nЧтобы вход по этим номерам работал без SMS, впишите в .env и перезапустите:"
        )
        self.stdout.write(f"OTP_TEST_NUMBERS={env_value}")

    def _demo_parcels(self, user, pickup):
        """Две посылки: одна лежит в ПВЗ (можно выдать), вторая в пути."""
        rows = (
            (f"TEST-PVZ-{pickup.id}-A", Parcel.Status.AT_PICKUP_POINT, pickup),
            (f"TEST-PVZ-{pickup.id}-B", Parcel.Status.SENT_TO_KYRGYZSTAN, None),
        )
        for track, status, at_pickup in rows:
            Parcel.objects.update_or_create(
                track_number=track,
                defaults=dict(
                    cargo=pickup.cargo,
                    user=user,
                    client_code=user.client_code,
                    status=status,
                    pickup_point=at_pickup,
                ),
            )
