from django.contrib import admin

from common.cargo_scoping import get_request_cargo_id

from .models import CargoCompany


@admin.register(CargoCompany)
class CargoCompanyAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "code", "phone", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("title", "slug", "code", "phone", "address")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at", "client_code_seq")
    fieldsets = (
        (None, {"fields": ("title", "slug", "code", "description", "logo", "is_active")}),
        ("Коды клиентов", {"fields": ("client_code_prefix", "client_code_seq")}),
        ("Контакты", {"fields": ("phone", "address")}),
        ("Даты", {"fields": ("created_at", "updated_at")}),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        cargo_id = get_request_cargo_id(request.user)
        if cargo_id:
            return qs.filter(pk=cargo_id)
        return qs.none()
