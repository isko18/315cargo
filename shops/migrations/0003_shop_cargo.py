# Generated manually for cargo multitenancy

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cargo", "0001_initial"),
        ("shops", "0002_alter_shop_options_alter_shop_client_code_strategy_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="shop",
            name="cargo",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="shops",
                to="cargo.cargocompany",
                verbose_name="Карго-центр",
            ),
        ),
        migrations.AlterField(
            model_name="shop",
            name="slug",
            field=models.SlugField(verbose_name="Идентификатор"),
        ),
    ]
