from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from notifications.models import NotificationType
from notifications.services import notify

from .models import Parcel, ParcelStatusHistory

# Тексты пушей по статусам: клиент видит понятную фразу, а не «Статус обновлён».
# Ключ — статус, значение — (заголовок, тело без трек-номера).
STATUS_MESSAGES = {
    Parcel.Status.ARRIVED_CHINA_WAREHOUSE: (
        "Посылка на складе в Китае",
        "принята на складе и готовится к отправке",
    ),
    Parcel.Status.PROCESSING: (
        "Посылка на обработке",
        "проходит классификацию и обработку на складе",
    ),
    Parcel.Status.ARRIVED_TOPA: (
        "Посылка прибыла в Топа",
        "прибыла на перевалочный склад",
    ),
    Parcel.Status.IN_TRANSIT: (
        "Посылка в пути",
        "выехала в Кыргызстан",
    ),
    Parcel.Status.CUSTOMS: (
        "Посылка на таможне",
        "проходит таможенное оформление",
    ),
    Parcel.Status.ARRIVED_KYRGYZSTAN: (
        "Посылка прибыла в Кыргызстан",
        "скоро будет в вашем пункте выдачи",
    ),
    Parcel.Status.ISSUED: (
        "Посылка выдана",
        "выдана — спасибо, что выбрали нас",
    ),
}


@receiver(pre_save, sender=Parcel)
def remember_old_status(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_status = None
        return
    instance._old_status = (
        Parcel.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
    )
    # Выдан → в архив (для полных сохранений: админка, импорт).
    if instance.status == Parcel.Status.ISSUED:
        instance.is_archived = True
    # Stamp arrived_at / issued_at on full saves (admin edits, CSV import).
    # Paths that save with update_fields handle it themselves.
    instance.apply_status_timestamps()


def _stamp_notified(parcel):
    """Отмечает, что клиенту ушло уведомление.

    Через .update(), а не save(): мы внутри post_save этой же посылки, и
    обычное сохранение ушло бы на второй круг сигнала.
    """
    from django.utils import timezone

    now = timezone.now()
    Parcel.objects.filter(pk=parcel.pk).update(notified_at=now)
    parcel.notified_at = now


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

    # Авто-шаги цепочки пишут историю, но не пушат клиенту (без спама).
    if getattr(instance, "_suppress_notification", False):
        return

    send_parcel_status_notification(instance)


def send_parcel_status_notification(parcel):
    """Уведомить клиента о текущем статусе посылки. Возвращает True, если ушло.

    Вынесено из сигнала, потому что нужно ещё в одном месте: когда «ничья»
    посылка находит хозяина (заказ приехал позже скана), клиент о ней ещё ничего
    не знает — уведомлять надо по уже имеющемуся статусу, без его смены.
    """
    if parcel.user_id is None:
        # Pending-посылки сканера ещё не привязаны к клиенту — уведомлять некого.
        return False

    display_name = parcel.get_status_display()
    data = {
        "parcel_id": parcel.id,
        "track_number": parcel.track_number,
        "status": parcel.status,
        "status_display_name": display_name,
    }

    if parcel.status == Parcel.Status.AT_PICKUP_POINT:
        notify(
            parcel.user,
            title="Посылка в ПВЗ",
            body=f"Посылка {parcel.track_number} прибыла в ПВЗ",
            type=NotificationType.PARCEL_AT_PICKUP_POINT,
            data=data,
        )
    else:
        title, phrase = STATUS_MESSAGES.get(
            parcel.status, ("Статус посылки обновлён", display_name.lower())
        )
        notify(
            parcel.user,
            title=title,
            body=f"Посылка {parcel.track_number} {phrase}",
            type=NotificationType.PARCEL_STATUS_CHANGED,
            data=data,
        )
    _stamp_notified(parcel)
    return True
