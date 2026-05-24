from django.contrib import admin

from .models import PinduoduoAccount


@admin.register(PinduoduoAccount)
class PinduoduoAccountAdmin(admin.ModelAdmin):
    list_display = ("user", "is_connected", "external_user_id", "last_sync_at", "created_at")
    list_filter = ("is_connected", "last_sync_at")
    search_fields = ("user__phone", "user__client_code", "external_user_id")
    raw_id_fields = ("user",)
