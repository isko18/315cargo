from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from notifications.models import NotificationType
from notifications.services import notify

from .models import Parcel, ParcelStatusHistory


@receiver(pre_save, sender=Parcel)
def remember_old_status(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_status = None
        return
    instance._old_status = (
        Parcel.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
    )


@receiver(post_save, sender=Parcel)
def create_status_history_and_notification(sender, instance, created, **kwargs):
    old_status = getattr(instance, "_old_status", None)
    status_unchanged = (not created) and old_status == instance.status
    if status_unchanged:
        return

    comment = getattr(instance, "_status_comment", "")
    changed_by = getattr(instance, "_status_changed_by", None)
    ParcelStatusHistory.objects.create(
        parcel=instance,
        status=instance.status,
        comment=comment,
        changed_by=changed_by,
    )

    display_name = instance.get_status_display()
    data = {
        "parcel_id": instance.id,
        "track_number": instance.track_number,
        "status": instance.status,
    }

    if instance.status == Parcel.Status.AT_PICKUP_POINT:
        notify(
            instance.user,
            title="Посылка в ПВЗ",
            body=f"Посылка {instance.track_number} прибыла в ПВЗ",
            type=NotificationType.PARCEL_AT_PICKUP_POINT,
            data=data,
        )
    else:
        notify(
            instance.user,
            title="Статус посылки обновлён",
            body=f"Посылка {instance.track_number}: {display_name}",
            type=NotificationType.PARCEL_STATUS_CHANGED,
            data=data,
        )
