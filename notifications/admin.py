from django.contrib import admin

from .models import DeviceToken, Notification, NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "type", "is_read", "created_at")
    list_filter = ("type", "is_read", "created_at")
    search_fields = ("user__phone", "user__client_code", "title", "body")
    raw_id_fields = ("user",)


@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "platform", "is_active", "created_at")
    list_filter = ("platform", "is_active")
    search_fields = ("user__phone", "user__client_code", "token")
    raw_id_fields = ("user",)


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "push_enabled",
        "parcel_status_enabled",
        "order_status_enabled",
        "city_delivery_enabled",
        "updated_at",
    )
    list_filter = ("push_enabled", "marketing_enabled")
    search_fields = ("user__phone", "user__client_code")
    raw_id_fields = ("user",)
