from django.contrib import admin

from .models import CityDeliveryPoint, CityDeliveryRequest, CityDeliveryTariff


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


@admin.register(CityDeliveryPoint)
class CityDeliveryPointAdmin(admin.ModelAdmin):
    list_display = ("title", "cargo", "address", "work_hours", "position", "is_active")
    list_filter = ("is_active", "cargo")
    search_fields = ("title", "address")


@admin.register(CityDeliveryRequest)
class CityDeliveryRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "delivery_point",
        "suggested_point",
        "is_standing",
        "status",
        "price",
        "courier",
        "delivery_date",
        "delivered_at",
        "created_at",
    )
    list_filter = ("status", "is_standing", "delivery_point", "delivery_date", "created_at")
    search_fields = (
        "user__phone",
        "user__client_code",
        "parcel__track_number",
        "parcels__track_number",
        "suggested_point",
        "recipient_phone",
        "recipient_name",
    )
    raw_id_fields = ("user", "parcel", "parcels", "courier", "tariff")
    readonly_fields = ("delivered_at", "created_at", "updated_at")
