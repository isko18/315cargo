# Generated manually for initial project setup.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("parcels", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CityDeliveryRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("address", models.TextField()),
                ("recipient_name", models.CharField(max_length=255)),
                ("recipient_phone", models.CharField(max_length=32)),
                ("comment", models.TextField(blank=True)),
                ("price", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("status", models.CharField(choices=[("created", "Created"), ("price_calculated", "Price calculated"), ("accepted", "Accepted"), ("assigned_to_courier", "Assigned to courier"), ("in_delivery", "In delivery"), ("delivered", "Delivered"), ("cancelled", "Cancelled")], default="created", max_length=32)),
                ("delivery_date", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("parcel", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="city_delivery_requests", to="parcels.parcel")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="city_delivery_requests", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        ),
    ]
