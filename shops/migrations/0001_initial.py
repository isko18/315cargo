# Generated manually for initial project setup.

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Shop",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("slug", models.SlugField(unique=True)),
                ("icon", models.ImageField(blank=True, null=True, upload_to="shop_icons/")),
                ("url", models.URLField()),
                ("open_type", models.CharField(choices=[("webview", "WebView"), ("external_app", "External app"), ("browser", "Browser")], default="webview", max_length=32)),
                ("client_code_strategy", models.CharField(choices=[("query_param", "Query param"), ("clipboard", "Clipboard"), ("manual_instruction", "Manual instruction")], default="query_param", max_length=32)),
                ("query_param_name", models.CharField(blank=True, max_length=64)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("sort_order", "title")},
        ),
    ]
