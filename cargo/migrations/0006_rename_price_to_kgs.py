"""Тариф карго переведён в сомы: price_per_kg_usd → price_per_kg_kgs.

Именно RenameField (а не remove+add, как предлагает автогенератор) — иначе
значения тарифов были бы потеряны. Сами суммы не пересчитываются: для этого
есть команда ``manage.py convert_prices_to_kgs --rate <курс>``.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cargo', '0005_client_code_prefix_unique'),
    ]

    operations = [
        migrations.RenameField(
            model_name='cargocompany',
            old_name='price_per_kg_usd',
            new_name='price_per_kg_kgs',
        ),
        migrations.AlterField(
            model_name='cargocompany',
            name='price_per_kg_kgs',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Стоимость доставки за 1 кг в сомах (KGS)', max_digits=8, verbose_name='Цена за кг, сом'),
        ),
    ]
