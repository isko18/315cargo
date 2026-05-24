from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html

from common.admin_mixins import CargoScopedAdminMixin

from .models import User


@admin.register(User)
class UserAdmin(CargoScopedAdminMixin, BaseUserAdmin):
    ordering = ("-created_at",)
    list_display = (
        "phone",
        "cargo",
        "full_name",
        "client_code",
        "pickup_point",
        "is_active",
        "is_staff",
        "is_cargo_admin",
        "created_at",
    )
    list_filter = ("is_active", "is_staff", "is_cargo_admin", "cargo", "pickup_point")
    search_fields = ("phone", "full_name", "client_code")
    readonly_fields = ("client_code", "qr_preview", "created_at", "updated_at", "last_login")
    autocomplete_fields = ("cargo", "pickup_point")
    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        (
            "Profile",
            {
                "fields": (
                    "cargo",
                    "full_name",
                    "pickup_point",
                    "client_code",
                    "qr_code_image",
                    "qr_preview",
                )
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_cargo_admin",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "phone",
                    "cargo",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_cargo_admin",
                    "is_superuser",
                ),
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            readonly.append("is_cargo_admin")
        return readonly

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "pickup_point":
            qs = db_field.remote_field.model.objects.all()
            if not request.user.is_superuser and request.user.cargo_id:
                qs = qs.filter(cargo_id=request.user.cargo_id)
            kwargs["queryset"] = qs
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def qr_preview(self, obj):
        if obj.qr_code_image:
            return format_html('<img src="{}" width="120" height="120" />', obj.qr_code_image.url)
        return "-"

    qr_preview.short_description = "QR code"
