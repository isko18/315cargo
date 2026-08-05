import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("cargo_backend")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "sync-pinduoduo-accounts-hourly": {
        "task": "integrations.sync_all_pinduoduo_accounts",
        "schedule": crontab(minute=0),
    },
    # Авто-статусы посылок (Китай → обработка → Топа → в пути → Кыргызстан).
    # Раз в минуту — чтобы короткий первый шаг (Китай→обработка, ~10с) срабатывал быстро.
    "advance-parcels-every-min": {
        "task": "parcels.advance_parcels",
        "schedule": crontab(minute="*"),
    },
}
