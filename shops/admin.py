from django.contrib import admin

from common.admin_mixins import CargoScopedAdminMixin

from .models import Shop


@admin.register(Shop)
class ShopAdmin(CargoScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        "title",
        "cargo",
        "slug",
        "open_type",
        "client_code_strategy",
        "sort_order",
        "is_active",
    )
    list_filter = ("cargo", "open_type", "client_code_strategy", "is_active")
    search_fields = ("title", "slug", "url")
    prepopulated_fields = {"slug": ("title",)}
    autocomplete_fields = ("cargo",)
