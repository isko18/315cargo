import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_cargo(apps, schema_editor):
    Parcel = apps.get_model("parcels", "Parcel")
    # Each existing parcel has a non-null user; copy the owner's cargo.
    for parcel in Parcel.objects.select_related("user").iterator():
        if parcel.user_id and parcel.user.cargo_id:
            parcel.cargo_id = parcel.user.cargo_id
            parcel.save(update_fields=["cargo"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("cargo", "0001_initial"),
        ("parcels", "0002_alter_parcel_options_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="parcel",
            name="cargo",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="parcels",
                to="cargo.cargocompany",
                verbose_name="Карго-центр",
            ),
        ),
        migrations.RunPython(backfill_cargo, noop),
        migrations.AlterField(
            model_name="parcel",
            name="cargo",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="parcels",
                to="cargo.cargocompany",
                verbose_name="Карго-центр",
            ),
        ),
        migrations.AlterField(
            model_name="parcel",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="parcels",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Клиент",
            ),
        ),
    ]
