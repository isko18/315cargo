import logging

from celery import shared_task

from .models import MarketplaceAccount

logger = logging.getLogger(__name__)


@shared_task(name="integrations.sync_pinduoduo_account")
def sync_pinduoduo_account(account_id: int):
    """Историческое имя задачи: синкает аккаунт любого маркетплейса по id."""
    from integrations.services import MarketplaceSyncService

    account = MarketplaceAccount.objects.select_related("user").filter(id=account_id).first()
    if not account or not account.is_connected:
        return {"skipped": True}
    service = MarketplaceSyncService(account.user, marketplace=account.marketplace)
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
        MarketplaceAccount.objects.filter(is_connected=True).values_list("id", flat=True)
    )
    for account_id in ids:
        sync_pinduoduo_account.delay(account_id)
    return {"scheduled": len(ids)}
