from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from notifications.models import NotificationType
from notifications.services import create_notification

from .models import User
from .services import generate_client_code, generate_qr_code


@receiver(post_save, sender=User)
def create_client_code_and_qr(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return
    if instance.client_code and instance.qr_code_image:
        if created:
            create_notification(
                user=instance,
                title="Добро пожаловать в 315CARGO!",
                body=(
                    f"Ваш клиентский код: {instance.client_code}. "
                    f"Покажите QR-код при получении заказов."
                ),
                type=NotificationType.AUTH,
                data={"client_code": instance.client_code},
            )
        return

    changed_fields = []
    if not instance.client_code:
        instance.client_code = generate_client_code(instance.cargo)
        changed_fields.append("client_code")
    if instance.client_code and not instance.qr_code_image:
        generate_qr_code(instance)
        changed_fields.append("qr_code_image")
    if changed_fields:
        User.objects.filter(pk=instance.pk).update(
            **{field: getattr(instance, field) for field in changed_fields}
        )

    if created:
        user = User.objects.get(pk=instance.pk)
        create_notification(
            user=user,
            title="Добро пожаловать в 315CARGO!",
            body=(
                f"Ваш клиентский код: {user.client_code}. "
                f"Покажите QR-код при получении заказов."
            ),
            type=NotificationType.AUTH,
            data={"client_code": user.client_code or ""},
        )


@receiver(post_delete, sender=User)
def delete_user_qr_file(sender, instance, **kwargs):
    if instance.qr_code_image:
        instance.qr_code_image.delete(save=False)
