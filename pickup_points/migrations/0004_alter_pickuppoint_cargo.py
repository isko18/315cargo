# Generated manually for cargo multitenancy

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pickup_points", "0003_pickuppoint_cargo"),
        ("users", "0005_user_cargo_multitenancy"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pickuppoint",
            name="cargo",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="pickup_points",
                to="cargo.cargocompany",
                verbose_name="Карго-центр",
            ),
        ),
    ]
