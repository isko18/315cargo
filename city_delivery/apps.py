from django.apps import AppConfig


class CityDeliveryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "city_delivery"

    def ready(self):
        import city_delivery.signals  # noqa: F401
