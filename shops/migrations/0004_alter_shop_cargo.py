# Generated manually for cargo multitenancy

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shops", "0003_shop_cargo"),
        ("users", "0005_user_cargo_multitenancy"),
    ]

    operations = [
        migrations.AlterField(
            model_name="shop",
            name="cargo",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="shops",
                to="cargo.cargocompany",
                verbose_name="Карго-центр",
            ),
        ),
        migrations.AddConstraint(
            model_name="shop",
            constraint=models.UniqueConstraint(
                fields=("cargo", "slug"),
                name="unique_shop_slug_per_cargo",
            ),
        ),
    ]
