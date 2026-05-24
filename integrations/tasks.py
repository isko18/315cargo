import logging

from celery import shared_task

from .models import PinduoduoAccount

logger = logging.getLogger(__name__)


@shared_task(name="integrations.sync_pinduoduo_account")
def sync_pinduoduo_account(account_id: int):
    from integrations.pinduoduo.services import PinduoduoSyncService

    account = PinduoduoAccount.objects.select_related("user").filter(id=account_id).first()
    if not account or not account.is_connected:
        return {"skipped": True}
    service = PinduoduoSyncService(account.user)
    result = service.sync_orders()
    return {
        "synced": result.synced,
        "created": result.created,
        "updated": result.updated,
        "errors": len(result.errors),
    }


@shared_task(name="integrations.sync_all_pinduoduo_accounts")
def sync_all_pinduoduo_accounts():
    ids = list(
        PinduoduoAccount.objects.filter(is_connected=True).values_list("id", flat=True)
    )
    for account_id in ids:
        sync_pinduoduo_account.delay(account_id)
    return {"scheduled": len(ids)}
