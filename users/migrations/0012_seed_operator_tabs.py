from django.db import migrations

from common.tabs import DEFAULT_OPERATOR_TABS


def seed_operator_tabs(apps, schema_editor):
    User = apps.get_model("users", "User")
    # Существующим операторам (staff, но не админ/китай/супер) выдаём базовый
    # набор вкладок, чтобы после введения прав они ничего не потеряли.
    for user in User.objects.filter(
        is_staff=True, is_cargo_admin=False, is_china_staff=False, is_superuser=False
    ):
        if not user.allowed_tabs:
            user.allowed_tabs = list(DEFAULT_OPERATOR_TABS)
            user.save(update_fields=["allowed_tabs"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("users", "0011_user_allowed_tabs")]
    operations = [migrations.RunPython(seed_operator_tabs, noop)]
