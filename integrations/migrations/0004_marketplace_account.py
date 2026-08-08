"""PinduoduoAccount → MarketplaceAccount: одна модель на все маркетплейсы.

RenameModel (а не удалить+создать) — иначе потерялись бы подключения клиентов.
OneToOne(user) заменяется на FK + уникальность по паре (user, marketplace):
один клиент может быть подключён и к Pinduoduo, и к Taobao одновременно.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("integrations", "0003_pdd_session_tracking"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="PinduoduoAccount",
            new_name="MarketplaceAccount",
        ),
        migrations.AlterModelOptions(
            name="marketplaceaccount",
            options={
                "ordering": ("-created_at",),
                "verbose_name": "Аккаунт маркетплейса",
                "verbose_name_plural": "Аккаунты маркетплейсов",
            },
        ),
        migrations.AddField(
            model_name="marketplaceaccount",
            name="marketplace",
            field=models.CharField(
                choices=[("pinduoduo", "Pinduoduo"), ("taobao", "Taobao")],
                db_index=True,
                default="pinduoduo",
                max_length=32,
                verbose_name="Маркетплейс",
            ),
        ),
        migrations.AlterField(
            model_name="marketplaceaccount",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="marketplace_accounts",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Клиент",
            ),
        ),
        migrations.AlterField(
            model_name="marketplaceaccount",
            name="external_user_id",
            field=models.CharField(
                blank=True, max_length=128, verbose_name="ID на стороне маркетплейса"
            ),
        ),
        migrations.AddConstraint(
            model_name="marketplaceaccount",
            constraint=models.UniqueConstraint(
                fields=("user", "marketplace"),
                name="unique_marketplace_account_per_user",
            ),
        ),
    ]
