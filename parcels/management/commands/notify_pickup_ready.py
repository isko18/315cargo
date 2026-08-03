from django.core.management.base import BaseCommand

from notifications.models import NotificationType
from notifications.services import notify
from parcels.models import Parcel


class Command(BaseCommand):
    help = (
        "Напоминает клиентам забрать посылки, которые лежат в ПВЗ "
        "(статус at_pickup_point, привязаны к клиенту). Запускать 2 раза в день."
    )

    def handle(self, *args, **options):
        qs = Parcel.objects.filter(
            status=Parcel.Status.AT_PICKUP_POINT,
            is_archived=False,
            user__isnull=False,
        ).select_related("user")

        sent = 0
        for parcel in qs.iterator():
            where = f", {parcel.location}" if parcel.location else ""
            notify(
                parcel.user,
                title="Заберите посылку",
                body=f"Посылка {parcel.track_number} ждёт вас в пункте выдачи{where}",
                type=NotificationType.PARCEL_AT_PICKUP_POINT,
                data={
                    "parcel_id": parcel.id,
                    "track_number": parcel.track_number,
                    "status": parcel.status,
                    "reminder": True,
                },
            )
            sent += 1

        self.stdout.write(self.style.SUCCESS(f"Отправлено напоминаний: {sent}"))
