from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "action",
        "actor",
        "target_user",
        "ip_address",
    )
    list_filter = ("action", "created_at")
    search_fields = (
        "actor__phone",
        "actor__client_code",
        "target_user__phone",
        "target_user__client_code",
        "description",
        "ip_address",
    )
    readonly_fields = (
        "actor",
        "target_user",
        "action",
        "description",
        "metadata",
        "ip_address",
        "user_agent",
        "created_at",
    )
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
