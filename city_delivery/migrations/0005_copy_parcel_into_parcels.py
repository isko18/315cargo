"""Заявки до переработки: единственная посылка переезжает и в состав parcels.

Новый код читает состав из parcels; без копирования старые заявки выглядели бы
пустыми — и в панели, и при синхронизации статусов посылок.
"""

from django.db import migrations


def copy_parcel(apps, schema_editor):
    Request = apps.get_model("city_delivery", "CityDeliveryRequest")
    Through = Request.parcels.through
    Through.objects.bulk_create(
        [
            Through(citydeliveryrequest_id=pk, parcel_id=parcel_id)
            for pk, parcel_id in Request.objects.filter(parcel__isnull=False).values_list(
                "pk", "parcel_id"
            )
        ],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    dependencies = [("city_delivery", "0004_delivery_points_and_parcels")]

    operations = [migrations.RunPython(copy_parcel, migrations.RunPython.noop)]
