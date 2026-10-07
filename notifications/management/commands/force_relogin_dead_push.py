"""Выкинуть из приложения клиентов, у которых не осталось ни одного рабочего push-токена.

Приложение присылает токен только при входе. Токен меняется при обновлении или
переустановке, а сессия остаётся (на iOS — даже после удаления приложения), так
что новый токен до сервера не доходит и push перестаёт приходить молча. Пока
приложение не начнёт слать токен при каждом запуске, вылечить таких клиентов
можно только повторным входом.

Аннулируем им сессию: все refresh-токены в чёрный список. Действующий
access-токен доживает своё (до часа), а при обновлении приложение получит 401,
уйдёт на экран входа, и вход зарегистрирует свежий токен.

Кого не трогаем:
  - сотрудников — приложение у них то же, выкинуть оператора посреди смены нельзя;
  - тестовые номера (OTP_TEST_NUMBERS);
  - клиента, у которого жив хотя бы один токен — ему push и так доходит;
  - клиента, по чьим токенам FCM не дал ответа (временный сбой) — по сбою не судим.
"""

from collections import defaultdict

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from common.audit import log_audit
from common.models import AuditLog
from notifications import services
from notifications.models import DeviceToken


class Command(BaseCommand):
    help = "Принудительный выход клиентов, у которых все push-токены мёртвые"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Выполнить выход. Без флага — только показать, кого затронет.",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        clients = (
            User.objects.filter(
                is_staff=False,
                is_superuser=False,
                is_cargo_admin=False,
                is_china_staff=False,
                device_tokens__is_active=True,
            )
            .exclude(phone__in=list(settings.OTP_TEST_NUMBERS.keys()))
            .distinct()
        )

        tokens_by_user = defaultdict(list)
        for user_id, token in DeviceToken.objects.filter(
            is_active=True, user__in=clients
        ).values_list("user_id", "token"):
            tokens_by_user[user_id].append(token)

        verdicts = services.probe_tokens(
            [t for tokens in tokens_by_user.values() for t in tokens]
        )

        dead_users = {}
        unknown = 0
        for user_id, tokens in tokens_by_user.items():
            states = [verdicts.get(t) for t in tokens]
            if any(s is True for s in states):
                continue
            if any(s is None for s in states):
                unknown += 1  # FCM не ответил внятно — не трогаем
                continue
            dead_users[user_id] = tokens

        self.stdout.write(f"Клиентов с активными токенами проверено: {len(tokens_by_user)}")
        self.stdout.write(f"Ни одного рабочего токена: {len(dead_users)}")
        if unknown:
            self.stdout.write(f"Пропущено из-за неясного ответа FCM: {unknown}")

        if not options["apply"]:
            self.stdout.write(
                self.style.WARNING("\nПредпросмотр. Для выхода — с --apply.")
            )
            return

        now = timezone.now()
        blacklisted = 0
        for user_id, tokens in dead_users.items():
            outstanding = OutstandingToken.objects.filter(
                user_id=user_id, expires_at__gt=now, blacklistedtoken__isnull=True
            )
            for token in outstanding:
                BlacklistedToken.objects.get_or_create(token=token)
                blacklisted += 1
            DeviceToken.objects.filter(user_id=user_id, token__in=tokens).update(
                is_active=False
            )
            log_audit(
                AuditLog.Action.USER_LOGOUT,
                target_user=User(pk=user_id),
                description="Принудительный выход: все push-токены мёртвые",
                metadata={"dead_tokens": len(tokens), "reason": "dead_push_tokens"},
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Выход выполнен: клиентов {len(dead_users)}, "
                f"аннулировано сессий {blacklisted}."
            )
        )
