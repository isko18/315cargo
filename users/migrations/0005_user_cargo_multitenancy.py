# Generated manually for cargo multitenancy

import django.db.models.deletion
from django.db import migrations, models


def assign_default_cargo(apps, schema_editor):
    CargoCompany = apps.get_model("cargo", "CargoCompany")
    PickupPoint = apps.get_model("pickup_points", "PickupPoint")
    Shop = apps.get_model("shops", "Shop")
    User = apps.get_model("users", "User")

    cargo, _ = CargoCompany.objects.get_or_create(
        slug="315cargo",
        defaults={
            "title": "315CARGO",
            "description": "Карго-центр по умолчанию",
            "is_active": True,
        },
    )
    PickupPoint.objects.filter(cargo__isnull=True).update(cargo_id=cargo.id)
    Shop.objects.filter(cargo__isnull=True).update(cargo_id=cargo.id)

    for user in User.objects.all():
        if user.is_superuser:
            user.login_key = f"su:{user.phone}"
        else:
            user.cargo_id = cargo.id
            user.login_key = f"{cargo.id}:{user.phone}"
        user.save(update_fields=["cargo_id", "login_key"])


class Migration(migrations.Migration):

    dependencies = [
        ("cargo", "0001_initial"),
        ("pickup_points", "0003_pickuppoint_cargo"),
        ("shops", "0003_shop_cargo"),
        ("users", "0004_otp_code_length_4"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="cargo",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="users",
                to="cargo.cargocompany",
                verbose_name="Карго-центр",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="login_key",
            field=models.CharField(
                editable=False,
                max_length=64,
                null=True,
                unique=True,
                verbose_name="Ключ входа",
            ),
        ),
        migrations.AlterField(
            model_name="user",
            name="phone",
            field=models.CharField(max_length=32, verbose_name="Телефон"),
        ),
        migrations.AlterField(
            model_name="user",
            name="client_code",
            field=models.CharField(
                blank=True,
                max_length=16,
                null=True,
                verbose_name="Клиентский код",
            ),
        ),
        migrations.RunPython(assign_default_cargo, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                fields=("cargo", "phone"),
                name="unique_user_phone_per_cargo",
            ),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                condition=models.Q(("client_code__isnull", False)),
                fields=("cargo", "client_code"),
                name="unique_user_client_code_per_cargo",
            ),
        ),
    ]
