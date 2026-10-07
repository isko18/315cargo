from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from notifications.models import NotificationType
from notifications.services import notify
from parcels.models import Parcel

from .models import CityDeliveryRequest
from .services import attach_to_standing_request


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
    # Служебные изменения — переоткрытие постоянной заявки, перенос посылки,
    # отмена самим клиентом — клиенту не о чем сообщать.
    if getattr(instance, "_silent", False):
        return
    data = {
        "city_delivery_id": instance.id,
        "parcel_id": instance.parcel_id,
        "status": instance.status,
    }
    if created:
        price = "Бесплатно" if not instance.price else f"Стоимость: {instance.price}"
        notify(
            instance.user,
            title="Заявка на доставку создана",
            body=f"Доставка: {instance.destination[:80]}. {price}",
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


@receiver(post_save, sender=Parcel)
def join_standing_request(sender, instance, **kwargs):
    """Посылка в ПВЗ у клиента с постоянной заявкой — едет вместе с ней."""
    if instance.status == Parcel.Status.AT_PICKUP_POINT and instance.user_id:
        attach_to_standing_request(instance)
