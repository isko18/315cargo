"""Сколько живут сессии Pinduoduo и от чего умирают.

Сессия PDD живёт в WebView мобильного приложения — сервер её не использует.
Но короткие сессии и баны бьют по клиентам, а без измерения причину не найти:
«клиент открыл официальное приложение PDD» и «куки не пережили перезапуск»
выглядят одинаково. Команда собирает факты из журнала аудита.

    manage.py pdd_session_stats            # за всё время
    manage.py pdd_session_stats --days 7   # только за неделю
"""

from collections import Counter, defaultdict
from datetime import timedelta
from statistics import median

from django.core.management.base import BaseCommand
from django.utils import timezone

from common.models import AuditLog
from integrations.models import PinduoduoAccount


def _fmt(minutes):
    if minutes is None:
        return "—"
    if minutes < 60:
        return f"{minutes:.0f} мин"
    return f"{minutes / 60:.1f} ч"


class Command(BaseCommand):
    help = "Статистика жизни сессий Pinduoduo: длительность и причины разлогина"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=0, help="Окно в днях (0 — всё)")

    def handle(self, *args, **options):
        days = options["days"]
        since = timezone.now() - timedelta(days=days) if days else None

        expired = AuditLog.objects.filter(
            action=AuditLog.Action.PINDUODUO_SESSION_EXPIRED
        )
        connects = AuditLog.objects.filter(
            action=AuditLog.Action.PINDUODUO_CONNECTED
        )
        if since:
            expired = expired.filter(created_at__gte=since)
            connects = connects.filter(created_at__gte=since)

        self.stdout.write(
            f"Окно: {'последние ' + str(days) + ' дн.' if days else 'всё время'}"
        )

        # --- Длительность сессий и причины (точные данные, с момента внедрения) ---
        lifetimes = []
        reasons = Counter()
        for row in expired.values_list("metadata", flat=True):
            reasons[(row or {}).get("reason") or "unknown"] += 1
            value = (row or {}).get("lifetime_minutes")
            if value is not None:
                lifetimes.append(float(value))

        self.stdout.write(self.style.MIGRATE_HEADING("\nРазлогины (точные замеры)"))
        if lifetimes:
            self.stdout.write(f"  событий: {len(lifetimes)}")
            self.stdout.write(f"  медиана жизни сессии: {_fmt(median(lifetimes))}")
            self.stdout.write(f"  минимум: {_fmt(min(lifetimes))}, максимум: {_fmt(max(lifetimes))}")
        else:
            self.stdout.write("  замеров пока нет (появятся после разлогинов уже с новой версией)")
        if reasons:
            self.stdout.write("  причины:")
            for reason, count in reasons.most_common():
                self.stdout.write(f"    {reason}: {count}")

        # --- Косвенная оценка по повторным входам (работает и на старых данных) ---
        by_user = defaultdict(list)
        for uid, ts in connects.order_by("target_user_id", "created_at").values_list(
            "target_user_id", "created_at"
        ):
            by_user[uid].append(ts)

        gaps = []
        quick = 0  # перелогины в пределах 10 минут — признак борьбы с антифродом
        for times in by_user.values():
            for a, b in zip(times, times[1:]):
                minutes = (b - a).total_seconds() / 60
                gaps.append(minutes)
                if minutes <= 10:
                    quick += 1

        self.stdout.write(self.style.MIGRATE_HEADING("\nПовторные входы (косвенно)"))
        self.stdout.write(f"  клиентов с логином PDD: {len(by_user)}")
        self.stdout.write(f"  всего входов: {sum(len(v) for v in by_user.values())}")
        if gaps:
            self.stdout.write(f"  медиана между входами: {_fmt(median(gaps))}")
            self.stdout.write(
                f"  входов подряд в пределах 10 мин: {quick}"
                + ("  ← так выглядит перебор для антифрода PDD" if quick else "")
            )

        # --- Текущее состояние аккаунтов ---
        accounts = PinduoduoAccount.objects.select_related("user").order_by("-updated_at")
        self.stdout.write(self.style.MIGRATE_HEADING("\nАккаунты"))
        for a in accounts:
            life = a.session_lifetime()
            life_txt = _fmt(life.total_seconds() / 60) if life else "—"
            state = "подключён" if a.is_connected else "разлогинен"
            self.stdout.write(
                f"  {a.user.phone}: {state}"
                f" | последняя сессия: {life_txt}"
                f" | причина: {a.last_expire_reason or '—'}"
            )
