from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from notifications.models import NotificationType
from notifications.services import notify

from .models import CityDeliveryRequest


@receiver(pre_save, sender=CityDeliveryRequest)
def remember_old_request_status(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_status = None
        return
    instance._old_status = (
        CityDeliveryRequest.objects.filter(pk=instance.pk)
        .values_list("status", flat=True)
        .first()
    )


@receiver(post_save, sender=CityDeliveryRequest)
def notify_city_delivery_changes(sender, instance, created, **kwargs):
    data = {
        "city_delivery_id": instance.id,
        "parcel_id": instance.parcel_id,
        "status": instance.status,
    }
    if created:
        notify(
            instance.user,
            title="Заявка на доставку создана",
            body=(
                f"Доставка по адресу: {instance.address[:80]}. "
                f"Стоимость: {instance.price or 'будет рассчитана'}"
            ),
            type=NotificationType.CITY_DELIVERY_CREATED,
            data=data,
        )
        return

    old_status = getattr(instance, "_old_status", None)
    if old_status == instance.status:
        return

    if (
        instance.status == CityDeliveryRequest.Status.DELIVERED
        and instance.delivered_at is None
    ):
        instance.delivered_at = timezone.now()
        CityDeliveryRequest.objects.filter(pk=instance.pk).update(
            delivered_at=instance.delivered_at
        )

    notify(
        instance.user,
        title="Статус доставки обновлён",
        body=f"Заявка #{instance.id}: {instance.get_status_display()}",
        type=NotificationType.CITY_DELIVERY_STATUS_CHANGED,
        data=data,
    )
