# Generated manually for initial project setup.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("orders", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Parcel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("track_number", models.CharField(max_length=128, unique=True)),
                ("client_code", models.CharField(db_index=True, max_length=16)),
                ("status", models.CharField(choices=[("created", "Оформлен"), ("purchased", "Выкуплен"), ("waiting_china_warehouse", "Ожидается на складе в Китае"), ("arrived_china_warehouse", "Прибыл на склад в Китае"), ("sent_to_kyrgyzstan", "Отправлен в Кыргызстан"), ("arrived_kyrgyzstan", "Прибыл в Кыргызстан"), ("at_pickup_point", "В ПВЗ"), ("city_delivery", "Передан на доставку по городу"), ("delivered", "Доставлен"), ("issued", "Выдан клиенту"), ("cancelled", "Отменен")], default="created", max_length=64)),
                ("location", models.CharField(blank=True, max_length=255)),
                ("weight", models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True)),
                ("volume", models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True)),
                ("delivery_price", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("arrived_at", models.DateTimeField(blank=True, null=True)),
                ("issued_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("order", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="parcels", to="orders.order")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="parcels", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="ParcelStatusHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("created", "Оформлен"), ("purchased", "Выкуплен"), ("waiting_china_warehouse", "Ожидается на складе в Китае"), ("arrived_china_warehouse", "Прибыл на склад в Китае"), ("sent_to_kyrgyzstan", "Отправлен в Кыргызстан"), ("arrived_kyrgyzstan", "Прибыл в Кыргызстан"), ("at_pickup_point", "В ПВЗ"), ("city_delivery", "Передан на доставку по городу"), ("delivered", "Доставлен"), ("issued", "Выдан клиенту"), ("cancelled", "Отменен")], max_length=64)),
                ("comment", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("changed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="parcel_status_changes", to=settings.AUTH_USER_MODEL)),
                ("parcel", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="history", to="parcels.parcel")),
            ],
            options={"ordering": ("-created_at",)},
        ),
    ]
