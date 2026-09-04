"""Перенумерация клиентских кодов под префикс ПВЗ.

Клиенты, зарегистрированные до включения своей нумерации у ПВЗ, носят код
карго. Команда переводит их на код ПВЗ, сохраняя порядок регистрации.

Операция необратимая и затрагивает то, по чему коробку опознают в Китае,
поэтому по умолчанию только показывает план (--apply включает запись).
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from parcels.models import Parcel
from pickup_points.models import PickupPoint
from users.models import User
from users.services import generate_qr_code


class Command(BaseCommand):
    help = "Перевести клиентов ПВЗ на его собственный префикс кода"

    def add_arguments(self, parser):
        parser.add_argument("--pickup", type=int, required=True, help="ID пункта выдачи")
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Записать изменения. Без флага — только показать план.",
        )

    def handle(self, *args, **options):
        point = PickupPoint.objects.filter(pk=options["pickup"]).first()
        if point is None:
            raise CommandError(f"ПВЗ id={options['pickup']} не найден")
        if not point.has_own_client_codes:
            raise CommandError(
                f"У ПВЗ «{point.title}» не задан client_code_prefix — "
                "нечего присваивать. Задайте префикс в панели."
            )

        prefix = point.client_code_prefix.strip()
        # Порядок регистрации: у кого код давно, у того и номер меньше.
        users = list(
            User.objects.filter(pickup_point=point, is_staff=False, is_superuser=False)
            .order_by("id")
        )
        if not users:
            self.stdout.write("Клиентов у этого ПВЗ нет.")
            return

        # Уже переведённых пропускаем: команда должна быть безопасна к повтору.
        pending = [u for u in users if not (u.client_code or "").startswith(prefix)]
        if not pending:
            self.stdout.write(self.style.SUCCESS("Все клиенты уже на префиксе ПВЗ."))
            return

        seq = point.client_code_seq
        plan = []
        for user in pending:
            seq += 1
            plan.append((user, user.client_code, point.format_client_code(seq)))

        # Столкновение внутри карго: код мог быть занят вручную в админке.
        new_codes = [new for _, _, new in plan]
        clash = (
            User.objects.filter(cargo=point.cargo, client_code__in=new_codes)
            .exclude(pk__in=[u.pk for u, _, _ in plan])
            .values_list("client_code", flat=True)
        )
        if clash:
            raise CommandError(f"Коды уже заняты другими клиентами: {sorted(clash)}")

        self.stdout.write(f"ПВЗ: {point.title} (id={point.id}), префикс {prefix}")
        self.stdout.write(f"Клиентов к переводу: {len(plan)} из {len(users)}\n")
        for user, old, new in plan:
            parcels = Parcel.objects.filter(user=user).count()
            name = (user.full_name or user.phone or "")[:28]
            self.stdout.write(f"  {old:<12} → {new:<12} {name:<30} посылок: {parcels}")

        if not options["apply"]:
            self.stdout.write(
                self.style.WARNING("\nЭто предпросмотр. Для записи повторите с --apply.")
            )
            return

        with transaction.atomic():
            for user, old, new in plan:
                user.client_code = new
                # QR кодирует сам код и лежит файлом с именем кода — без
                # перегенерации клиент показал бы на выдаче старый код.
                generate_qr_code(user)
                user.save(update_fields=("client_code", "qr_code_image"))
                # На посылке код продублирован: без обновления поиск по коду
                # перестал бы находить уже принятые посылки этого клиента.
                Parcel.objects.filter(user=user, client_code=old).update(client_code=new)
            point.client_code_seq = seq
            point.save(update_fields=("client_code_seq",))

        self.stdout.write(self.style.SUCCESS(f"\nГотово. Переведено: {len(plan)}."))
        self.stdout.write(f"Счётчик ПВЗ: {point.client_code_seq}")
