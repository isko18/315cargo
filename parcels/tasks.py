from celery import shared_task


@shared_task(name="parcels.advance_parcels")
def advance_parcels_task():
    """Продвигает посылки по авто-цепочке статусов (после 1-го скана в Китае
    и до 2-го скана в ПВЗ). Запускается Celery beat периодически."""
    from parcels.services import advance_all_parcels

    moved = advance_all_parcels()
    return {"moved": moved}
