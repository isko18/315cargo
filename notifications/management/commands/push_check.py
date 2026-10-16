"""Почему клиенту не пришёл пуш — разбор по номеру или коду.

Жалоба «не пришёл пуш» почти всегда про конкретного человека, а причин
несколько, и снаружи они неотличимы:

* клиент сам выключил пуши или статусы посылок в настройках приложения;
* у него нет ни одного токена — приложение ни разу не зарегистрировало
  устройство (не дал разрешение, не входил после переустановки);
* токен есть, но мёртвый — приложение переустановлено, токен сменился;
* с сервера всё ушло, и тогда искать надо на устройстве.

Проверка токена идёт через FCM dry_run: Google валидирует токен, но клиенту
ничего не доставляет — команду можно гонять по живым людям.

    manage.py push_check +996700123456
    manage.py push_check ISIM0042 +996555000111
    manage.py push_check --days 3          # сводка по получателям «в ПВЗ»
"""

from collections import Counter
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from notifications.models import DeviceToken, Notification, NotificationType
from notifications.services import _ensure_firebase_initialized, get_or_create_preference

User = get_user_model()

PARCEL_TYPES = (NotificationType.PARCEL_AT_PICKUP_POINT, NotificationType.PARCEL_STATUS_CHANGED)


def dry_run(tokens):
    """{token: None | текст ошибки}. Ничего не доставляет — только проверка."""
    if not tokens:
        return {}
    from firebase_admin import messaging

    result = {}
    for i in range(0, len(tokens), 500):
        chunk = tokens[i : i + 500]
        message = messaging.MulticastMessage(
            tokens=chunk, notification=messaging.Notification(title="check", body="check")
        )
        response = messaging.send_each_for_multicast(message, dry_run=True)
        for token, item in zip(chunk, response.responses):
            result[token] = None if item.success else str(item.exception)
    return result


class Command(BaseCommand):
    help = "Разобрать, почему клиенту не приходят пуши (номер или код клиента)"

    def add_arguments(self, parser):
        parser.add_argument("who", nargs="*", help="Телефон или код клиента")
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help="Без номеров: сводка по всем, кому за N дней ушло «Посылка в ПВЗ»",
        )

    def handle(self, *args, **options):
        if not _ensure_firebase_initialized():
            raise CommandError("FCM не настроен (FCM_CREDENTIALS_PATH) — пуши не уходят никому")

        if options["who"]:
            for who in options["who"]:
                self._one(who.strip())
        else:
            self._summary(options["days"] or 3)

    # --- Один клиент ---

    def _one(self, who):
        users = list(
            User.objects.filter(Q(phone=who) | Q(client_code__iexact=who))
            .select_related("cargo", "pickup_point")
            .order_by("id")
        )
        self.stdout.write("")
        if not users:
            self.stdout.write(self.style.ERROR(f"{who}: клиент не найден"))
            return
        for user in users:
            self._report(user)

    def _report(self, user):
        w = self.stdout.write
        w(self.style.MIGRATE_HEADING(
            f"{user.phone} · {user.client_code or '—'} · {user.full_name or 'без имени'}"
            f" · карго {getattr(user.cargo, 'title', '—')}"
            f"{' · СОТРУДНИК' if user.is_staff else ''}"
        ))

        pref = get_or_create_preference(user)
        tokens = list(DeviceToken.objects.filter(user=user).order_by("-updated_at"))
        live = [t.token for t in tokens if t.is_active]
        checked = dry_run(live)

        w(f"  пуши включены: {'да' if pref.push_enabled else 'НЕТ'}"
          f" · статусы посылок: {'да' if pref.parcel_status_enabled else 'НЕТ'}")
        if not tokens:
            w("  токенов: нет ни одного")
        for t in tokens:
            if not t.is_active:
                state = "отключён сервером"
            elif checked.get(t.token) is None:
                state = "рабочий"
            else:
                state = f"МЁРТВЫЙ ({checked[t.token]})"
            w(f"  {t.platform:8} обновлён {timezone.localtime(t.updated_at):%d.%m %H:%M}"
              f"  …{t.token[-10:]}  {state}")

        recent = Notification.objects.filter(user=user, type__in=PARCEL_TYPES).order_by("-created_at")[:5]
        for n in recent:
            w(f"  {timezone.localtime(n.created_at):%d.%m %H:%M}  {n.title} — {n.body}")
        if not recent:
            w("  уведомлений о посылках не было")

        working = [t for t in live if checked.get(t) is None]
        w("  ИТОГ: " + self._verdict(pref, tokens, working))

    def _verdict(self, pref, tokens, working):
        if not pref.push_enabled:
            return self.style.WARNING("клиент сам выключил пуши в приложении")
        if not pref.parcel_status_enabled:
            return self.style.WARNING(
                "выключены «статусы посылок» — нет ни пуша, ни записи в приложении"
            )
        if not tokens:
            return self.style.WARNING(
                "устройство ни разу не зарегистрировано: не дал разрешение на уведомления "
                "или не входил после установки"
            )
        if not working:
            return self.style.WARNING(
                "все токены мёртвые — приложение переустановлено; нужно выйти и войти заново"
            )
        return self.style.SUCCESS(
            "с сервера доходит до Google/Apple — искать на телефоне: разрешение на "
            "уведомления в настройках ОС, режим «Не беспокоить», энергосбережение"
        )

    # --- Сводка ---

    def _summary(self, days):
        w = self.stdout.write
        since = timezone.now() - timedelta(days=days)
        users = set(
            Notification.objects.filter(
                type=NotificationType.PARCEL_AT_PICKUP_POINT, created_at__gte=since
            ).values_list("user_id", flat=True)
        )
        tokens = list(
            DeviceToken.objects.filter(user_id__in=users, is_active=True).values_list(
                "token", "platform", "user_id"
            )
        )
        checked = dry_run([t for t, _, _ in tokens])
        ok_users = {uid for t, _, uid in tokens if checked.get(t) is None}
        reasons = Counter(
            f"{plat}: {checked[t]}" for t, plat, _ in tokens if checked.get(t) is not None
        )

        w(f"«Посылка в ПВЗ» за {days} дн.: клиентов {len(users)}")
        w(f"  с рабочим токеном: {len(ok_users)}")
        w(f"  пуш не дойдёт: {len(users - ok_users)}")
        for reason, count in reasons.most_common(5):
            w(f"    {count} × {reason}")
        lost = User.objects.filter(id__in=users - ok_users).order_by("phone")[:30]
        for user in lost:
            w(f"    {user.phone}  {user.client_code or '—'}  {user.full_name}")
