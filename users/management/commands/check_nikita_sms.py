from django.core.management.base import BaseCommand

from users.sms.diagnostics import check_nikita_account


class Command(BaseCommand):
    help = "Проверить логин/пароль и баланс аккаунта Nikita SMS"

    def handle(self, *args, **options):
        result = check_nikita_account()
        if result.get("ok"):
            self.stdout.write(self.style.SUCCESS("Nikita SMS: авторизация OK"))
            self.stdout.write(f"  Баланс: {result.get('account')}")
            self.stdout.write(f"  Цена SMS: {result.get('smsprice')}")
            self.stdout.write(f"  Sender: {result.get('sender')}")
            self.stdout.write(f"  Test mode: {result.get('test_mode')}")
            return
        self.stdout.write(self.style.ERROR(f"Nikita SMS: {result.get('error', 'ошибка')}"))
        self.stdout.write(f"  status: {result.get('status')} ({result.get('status_text')})")
        if result.get("status") == 2:
            self.stdout.write(
                "  Prover'te login i parol v .env (kabinet smspro.nikita.kg, razdel Parametry API)"
            )
        if result.get("status") == 3:
            self.stdout.write(
                "  Dobav'te IP servera v whitelist v kabinete Nikita"
            )
        if result.get("status") == 4:
            self.stdout.write(
                "  Popolnite balans ili vklyuchite NIKITA_SMS_TEST=1 v .env"
            )
            self.stdout.write(
                "  Na testovom akkaunte API rabotaet tol'ko s nomerom iz profilya Nikita"
            )
            self.stdout.write(
                "  Ukazhite ego v NIKITA_SMS_ALLOWED_PHONE (+996...)"
            )
