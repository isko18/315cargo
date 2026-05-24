from django.contrib import admin

from common.admin_mixins import CargoScopedAdminMixin

from .models import PickupPoint


@admin.register(PickupPoint)
class PickupPointAdmin(CargoScopedAdminMixin, admin.ModelAdmin):
    list_display = ("title", "cargo", "phone", "is_active", "created_at")
    list_filter = ("is_active", "cargo")
    search_fields = ("title", "address", "phone")
    autocomplete_fields = ("cargo",)
