from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from common.admin_mixins import CargoScopedAdminMixin
from common.audit import log_audit
from common.models import AuditLog

from .imports import import_parcels_from_csv
from .models import Parcel, ParcelStatusHistory


class ParcelImportForm(forms.Form):
    csv_file = forms.FileField(
        label="CSV-файл",
        help_text=(
            "Колонки: track_number,client_code,status,location,weight,volume,delivery_price. "
            "Кодировка UTF-8."
        ),
    )
    encoding = forms.CharField(initial="utf-8", required=False)


class ParcelStatusHistoryInline(admin.TabularInline):
    model = ParcelStatusHistory
    extra = 0
    readonly_fields = ("status", "comment", "changed_by", "created_at")
    can_delete = False


@admin.register(Parcel)
class ParcelAdmin(CargoScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        "track_number",
        "cargo",
        "user",
        "client_code",
        "status",
        "location",
        "weight",
        "delivery_price",
        "created_at",
    )
    list_filter = ("status", "cargo", "created_at")
    search_fields = (
        "track_number",
        "client_code",
        "user__phone",
        "user__client_code",
    )
    raw_id_fields = ("cargo", "user", "order")
    inlines = (ParcelStatusHistoryInline,)
    change_list_template = "admin/parcels/parcel/change_list.html"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "import-csv/",
                self.admin_site.admin_view(self.import_csv_view),
                name="parcels_parcel_import_csv",
            ),
        ]
        return custom + urls

    def import_csv_view(self, request):
        if request.method == "POST":
            form = ParcelImportForm(request.POST, request.FILES)
            if form.is_valid():
                encoding = form.cleaned_data.get("encoding") or "utf-8"
                # Scope the client_code lookup to the importing admin's cargo so
                # parcels cannot be attached to clients in another cargo. A
                # global superuser (no cargo) imports across all cargos.
                import_cargo = None if request.user.is_superuser else request.user.cargo
                result = import_parcels_from_csv(
                    request.FILES["csv_file"], encoding=encoding, cargo=import_cargo
                )
                log_audit(
                    AuditLog.Action.PARCEL_IMPORTED,
                    actor=request.user,
                    description=f"Импортирован CSV ({request.FILES['csv_file'].name})",
                    metadata={
                        "created": result.created,
                        "updated": result.updated,
                        "skipped": result.skipped,
                        "errors": len(result.errors),
                    },
                    request=request,
                )
                msg = (
                    f"Импорт: создано {result.created}, обновлено {result.updated}, "
                    f"пропущено {result.skipped}"
                )
                level = messages.SUCCESS if not result.errors else messages.WARNING
                self.message_user(request, msg, level=level)
                for err in result.errors[:20]:
                    self.message_user(request, err, level=messages.ERROR)
                if len(result.errors) > 20:
                    self.message_user(
                        request,
                        f"...и ещё {len(result.errors) - 20} ошибок",
                        level=messages.ERROR,
                    )
                return redirect(reverse("admin:parcels_parcel_changelist"))
        else:
            form = ParcelImportForm()
        context = {
            **self.admin_site.each_context(request),
            "title": "Импорт посылок из CSV",
            "form": form,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/parcels/parcel/import_csv.html", context)


@admin.register(ParcelStatusHistory)
class ParcelStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("parcel", "status", "changed_by", "created_at")
    list_filter = ("status", "created_at")
    search_fields = (
        "parcel__track_number",
        "parcel__client_code",
        "changed_by__phone",
    )
    raw_id_fields = ("parcel", "changed_by")
