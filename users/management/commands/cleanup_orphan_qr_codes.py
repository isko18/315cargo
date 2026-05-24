from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from users.models import User


class Command(BaseCommand):
    help = "Удалить QR-файлы, не привязанные к существующим клиентам"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только показать, что будет удалено",
        )

    def handle(self, *args, **options):
        qr_dir = Path(settings.MEDIA_ROOT) / "qr_codes"
        if not qr_dir.exists():
            self.stdout.write("Папка qr_codes не найдена")
            return

        active_names = {
            Path(user.qr_code_image.name).name
            for user in User.objects.exclude(qr_code_image="")
            if user.qr_code_image
        }
        removed = 0
        for path in qr_dir.iterdir():
            if not path.is_file():
                continue
            if path.name in active_names:
                continue
            if options["dry_run"]:
                self.stdout.write(f"  удалить: {path.name}")
            else:
                path.unlink(missing_ok=True)
            removed += 1

        action = "Будет удалено" if options["dry_run"] else "Удалено"
        self.stdout.write(
            self.style.SUCCESS(f"{action} файлов: {removed}. Активных QR: {len(active_names)}")
        )
