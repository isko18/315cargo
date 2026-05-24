# Generated manually for cargo multitenancy

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cargo", "0001_initial"),
        ("pickup_points", "0002_alter_pickuppoint_options_alter_pickuppoint_address_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="pickuppoint",
            name="cargo",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="pickup_points",
                to="cargo.cargocompany",
                verbose_name="Карго-центр",
            ),
        ),
    ]
