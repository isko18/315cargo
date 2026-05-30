from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from common.admin_mixins import CargoScopedAdminMixin
from common.cargo_scoping import get_request_cargo_id

from .models import SMSCode, User


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
            cargo_id = get_request_cargo_id(request.user)
            if not request.user.is_superuser and cargo_id:
                qs = qs.filter(cargo_id=cargo_id)
            kwargs["queryset"] = qs
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def qr_preview(self, obj):
        if obj.qr_code_image:
            return format_html('<img src="{}" width="120" height="120" />', obj.qr_code_image.url)
        return "-"

    qr_preview.short_description = "QR code"


@admin.register(SMSCode)
class SMSCodeAdmin(admin.ModelAdmin):
    list_display = (
        "phone",
        "code_display",
        "purpose",
        "status_display",
        "expires_at",
        "created_at",
    )
    list_filter = ("purpose", "is_used", "created_at")
    search_fields = ("phone", "code", "provider_message_id")
    readonly_fields = (
        "phone",
        "code_display",
        "purpose",
        "is_used",
        "status_display",
        "expires_at",
        "provider_message_id",
        "created_at",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "phone",
                    "code_display",
                    "purpose",
                    "status_display",
                    "is_used",
                    "expires_at",
                    "provider_message_id",
                    "created_at",
                )
            },
        ),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def code_display(self, obj):
        if obj.is_used or obj.is_expired:
            color = "#94a3b8"
            background = "#f8fafc"
        else:
            color = "#15803d"
            background = "#f0fdf4"
        return format_html(
            '<span style="font-family: monospace; font-size: 18px; font-weight: 700; '
            'letter-spacing: 0.25em; color: {}; background: {}; padding: 4px 10px; '
            'border-radius: 6px;">{}</span>',
            color,
            background,
            obj.code,
        )

    code_display.short_description = _("Код")

    def status_display(self, obj):
        if obj.is_used:
            label = _("Использован")
            color = "#64748b"
            background = "#f1f5f9"
        elif obj.is_expired:
            label = _("Истёк")
            color = "#b45309"
            background = "#fffbeb"
        else:
            label = _("Активен")
            color = "#15803d"
            background = "#f0fdf4"
        return format_html(
            '<span style="color: {}; background: {}; padding: 2px 8px; '
            'border-radius: 999px; font-size: 12px; font-weight: 600;">{}</span>',
            color,
            background,
            label,
        )

    status_display.short_description = _("Статус")
