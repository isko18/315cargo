from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from notifications.models import NotificationType
from notifications.services import notify

from .models import Order


@receiver(pre_save, sender=Order)
def remember_old_order_status(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_status = None
        return
    instance._old_status = (
        Order.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
    )


@receiver(post_save, sender=Order)
def notify_order_changes(sender, instance, created, **kwargs):
    title_fallback = (
        instance.product_title
        or instance.external_order_id
        or f"Заказ #{instance.id}"
    )

    if created:
        notify(
            instance.user,
            title="Новый заказ",
            body=f"Создан заказ: {title_fallback}",
            type=NotificationType.ORDER_CREATED,
            data={
                "order_id": instance.id,
                "source": instance.source,
                "status": instance.status,
            },
        )
        return

    old_status = getattr(instance, "_old_status", None)
    if old_status == instance.status:
        return

    notify(
        instance.user,
        title="Статус заказа обновлён",
        body=f"{title_fallback}: {instance.get_status_display()}",
        type=NotificationType.ORDER_STATUS_CHANGED,
        data={
            "order_id": instance.id,
            "status": instance.status,
        },
    )
