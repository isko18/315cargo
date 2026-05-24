# Generated manually for initial project setup.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Order",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(choices=[("pinduoduo", "Pinduoduo"), ("taobao", "Taobao"), ("1688", "1688"), ("manual", "Manual")], default="manual", max_length=32)),
                ("external_order_id", models.CharField(blank=True, max_length=128)),
                ("product_url", models.URLField(blank=True)),
                ("product_title", models.CharField(blank=True, max_length=255)),
                ("price", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("quantity", models.PositiveIntegerField(default=1)),
                ("status", models.CharField(choices=[("created", "Created"), ("paid", "Paid"), ("purchased", "Purchased"), ("waiting_china_warehouse", "Waiting China warehouse"), ("arrived_china_warehouse", "Arrived China warehouse"), ("cancelled", "Cancelled")], default="created", max_length=64)),
                ("track_number", models.CharField(blank=True, db_index=True, max_length=128)),
                ("raw_data", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="orders", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        ),
    ]
