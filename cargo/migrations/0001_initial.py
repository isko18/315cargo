# Generated manually for cargo multitenancy

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="CargoCompany",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(max_length=255, verbose_name="Название")),
                (
                    "slug",
                    models.SlugField(unique=True, verbose_name="Идентификатор"),
                ),
                ("description", models.TextField(blank=True, verbose_name="Описание")),
                (
                    "logo",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to="cargo_logos/",
                        verbose_name="Логотип",
                    ),
                ),
                (
                    "phone",
                    models.CharField(blank=True, max_length=32, verbose_name="Телефон"),
                ),
                ("address", models.TextField(blank=True, verbose_name="Адрес")),
                ("is_active", models.BooleanField(default=True, verbose_name="Активен")),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Создан"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Обновлён"),
                ),
            ],
            options={
                "verbose_name": "Карго-центр",
                "verbose_name_plural": "Карго-центры",
                "ordering": ("title",),
            },
        ),
    ]
