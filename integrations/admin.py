from django.contrib import admin

from .models import MarketplaceAccount


@admin.register(MarketplaceAccount)
class MarketplaceAccountAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "marketplace",
        "is_connected",
        "session_lifetime",
        "last_expire_reason",
        "last_sync_at",
        "created_at",
    )
    list_filter = ("is_connected", "last_sync_at")
    search_fields = ("user__phone", "user__client_code", "external_user_id")
    raw_id_fields = ("user",)
