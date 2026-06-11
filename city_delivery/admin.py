from django.contrib import admin

from .models import CityDeliveryRequest, CityDeliveryTariff


@admin.register(CityDeliveryTariff)
class CityDeliveryTariffAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "base_price",
        "price_per_kg",
        "free_weight_kg",
        "min_price",
        "cargo",
        "pickup_point",
        "is_default",
        "is_active",
    )
    list_filter = ("is_default", "is_active", "cargo", "pickup_point")
    search_fields = ("title",)


@admin.register(CityDeliveryRequest)
class CityDeliveryRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "parcel",
        "status",
        "price",
        "tariff",
        "courier",
        "delivery_date",
        "delivered_at",
        "created_at",
    )
    list_filter = ("status", "delivery_date", "created_at", "tariff")
    search_fields = (
        "user__phone",
        "user__client_code",
        "parcel__track_number",
        "recipient_phone",
        "recipient_name",
    )
    raw_id_fields = ("user", "parcel", "courier", "tariff")
    autocomplete_fields = ()
    readonly_fields = ("delivered_at", "created_at", "updated_at")
