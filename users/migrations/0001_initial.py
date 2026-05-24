# Generated manually for initial project setup.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("pickup_points", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="SMSCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phone", models.CharField(db_index=True, max_length=32)),
                ("code", models.CharField(max_length=6)),
                ("purpose", models.CharField(choices=[("register", "Register"), ("login", "Login")], max_length=16)),
                ("is_used", models.BooleanField(default=False)),
                ("expires_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="User",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                ("last_login", models.DateTimeField(blank=True, null=True, verbose_name="last login")),
                ("is_superuser", models.BooleanField(default=False)),
                ("phone", models.CharField(max_length=32, unique=True)),
                ("full_name", models.CharField(blank=True, max_length=255)),
                ("client_code", models.CharField(blank=True, max_length=16, null=True, unique=True)),
                ("qr_code_image", models.ImageField(blank=True, null=True, upload_to="qr_codes/")),
                ("is_active", models.BooleanField(default=True)),
                ("is_staff", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("groups", models.ManyToManyField(blank=True, related_name="user_set", related_query_name="user", to="auth.group")),
                ("user_permissions", models.ManyToManyField(blank=True, related_name="user_set", related_query_name="user", to="auth.permission")),
                ("pickup_point", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="users", to="pickup_points.pickuppoint")),
            ],
            options={"ordering": ("-created_at",)},
        ),
    ]
