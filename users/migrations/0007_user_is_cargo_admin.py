# Generated manually

from django.db import migrations, models


CARGO_ADMIN_GROUP = "Администратор карго"

CARGO_ADMIN_PERMISSIONS = [
    ("users", "user", "view_user"),
    ("users", "user", "add_user"),
    ("users", "user", "change_user"),
    ("pickup_points", "pickuppoint", "view_pickuppoint"),
    ("pickup_points", "pickuppoint", "add_pickuppoint"),
    ("pickup_points", "pickuppoint", "change_pickuppoint"),
    ("shops", "shop", "view_shop"),
    ("shops", "shop", "add_shop"),
    ("shops", "shop", "change_shop"),
    ("orders", "order", "view_order"),
    ("orders", "order", "change_order"),
    ("parcels", "parcel", "view_parcel"),
    ("parcels", "parcel", "change_parcel"),
    ("city_delivery", "citydeliverytariff", "view_citydeliverytariff"),
    ("city_delivery", "citydeliverytariff", "change_citydeliverytariff"),
    ("city_delivery", "citydeliveryrequest", "view_citydeliveryrequest"),
    ("city_delivery", "citydeliveryrequest", "change_citydeliveryrequest"),
    ("cargo", "cargocompany", "view_cargocompany"),
    ("cargo", "cargocompany", "change_cargocompany"),
]


def create_cargo_admin_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    group, _ = Group.objects.get_or_create(name=CARGO_ADMIN_GROUP)
    permission_ids = []
    for app_label, model, codename in CARGO_ADMIN_PERMISSIONS:
        content_type = ContentType.objects.filter(app_label=app_label, model=model).first()
        if not content_type:
            continue
        permission = Permission.objects.filter(
            content_type=content_type,
            codename=codename,
        ).first()
        if permission:
            permission_ids.append(permission.id)
    group.permissions.set(permission_ids)


def remove_cargo_admin_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=CARGO_ADMIN_GROUP).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0006_alter_user_login_key"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_cargo_admin",
            field=models.BooleanField(
                default=False,
                help_text="Полный доступ к управлению своим карго-центром в админке и API",
                verbose_name="Администратор карго",
            ),
        ),
        migrations.RunPython(create_cargo_admin_group, remove_cargo_admin_group),
    ]
