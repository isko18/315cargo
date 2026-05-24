from django.contrib import admin

from .models import Order


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "source", "status", "track_number", "created_at")
    list_filter = ("source", "status", "created_at")
    search_fields = ("user__phone", "user__client_code", "track_number", "external_order_id", "product_title")
    raw_id_fields = ("user",)
