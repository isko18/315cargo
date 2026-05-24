from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from notifications.services import send_push_notification

User = get_user_model()


class Command(BaseCommand):
    help = "Отправить тестовое push-уведомление пользователю по client_code"

    def add_arguments(self, parser):
        parser.add_argument("client_code")
        parser.add_argument("--title", default="Тест 315CARGO")
        parser.add_argument("--body", default="Это тестовое уведомление")

    def handle(self, *args, **options):
        user = User.objects.filter(client_code=options["client_code"]).first()
        if not user:
            raise CommandError("Клиент с таким кодом не найден")
        result = send_push_notification(
            user, options["title"], options["body"], data={"source": "cli"}
        )
        self.stdout.write(self.style.SUCCESS(f"Push отправлен: {result}"))
