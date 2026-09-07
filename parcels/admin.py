from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from common.admin_mixins import CargoScopedAdminMixin, get_request_cargo_id
from pickup_points.models import PickupPoint
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
        "product_thumb",
        "track_number",
        "product_title",
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

    @admin.display(description="Товар")
    def product_title(self, obj):
        return (obj.order.product_title or "")[:60] if obj.order_id else "-"

    @admin.display(description="Фото")
    def product_thumb(self, obj):
        raw = getattr(obj.order, "raw_data", None) if obj.order_id else None
        goods = raw.get("order_goods") if isinstance(raw, dict) else None
        url = None
        if isinstance(goods, list) and goods and isinstance(goods[0], dict):
            url = goods[0].get("thumb_url") or goods[0].get("hd_thumb_url")
        if url:
            return format_html('<img src="{}" style="height:40px;border-radius:4px"/>', url)
        return "-"
    search_fields = (
        "track_number",
        "client_code",
        "user__phone",
        "user__client_code",
    )
    raw_id_fields = ("cargo", "user", "order")

    @admin.display(description="Код клиента (в карточке клиента)")
    def user_client_code(self, obj):
        """Код из карточки клиента — источник правды.

        Поле client_code на посылке это копия на момент приёмки. Копия и
        оригинал расходятся, например, после перенумерации ПВЗ, и тогда по
        форме непонятно, какой код настоящий.
        """
        if obj.user_id is None:
            return "— посылка без клиента"
        actual = obj.user.client_code or "—"
        if obj.client_code and obj.client_code != actual:
            return format_html(
                '{} <b style="color:#b00">(на посылке: {})</b>', actual, obj.client_code
            )
        return actual

    @admin.display(description="ПВЗ клиента (действует сейчас)")
    def user_pickup_point(self, obj):
        """ПВЗ из карточки клиента и пояснение, какой ПВЗ реально в силе.

        Поле «ПВЗ» у посылки — это где её физически приняли, и до приёмки оно
        пустое. Пустое поле читается как «ПВЗ не выбран», хотя система в этот
        момент везде использует ПВЗ клиента:
        Q(pickup_point=X) | Q(pickup_point=None, user__pickup_point=X).
        """
        if obj.user_id is None:
            return "— посылка без клиента"
        client_pp = obj.user.pickup_point
        if client_pp is None:
            return "— у клиента ПВЗ не задан"
        if obj.pickup_point_id:
            if obj.pickup_point_id == client_pp.id:
                return f"{client_pp} — совпадает с ПВЗ приёмки"
            return format_html(
                '{} <b style="color:#b00">(принята в другом: {})</b>',
                client_pp,
                obj.pickup_point,
            )
        return format_html(
            "{} <span style='color:#666'>— посылка числится за ним, пока не принята</span>",
            client_pp,
        )

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if obj is not None:
            # На существующей посылке код правится только через привязку
            # клиента: ручная правка копии разъезжается с карточкой клиента.
            # На форме создания поле обязательное, поэтому там оставляем.
            ro += ["client_code", "user_client_code", "user_pickup_point"]
        return ro

    def get_fields(self, request, obj=None):
        """Справку из карточки клиента ставим вплотную к соответствующему полю.

        Раньше обе вставлялись после client_code, и пояснение про ПВЗ
        оказывалось далеко от самого поля «ПВЗ» — читать его было незачем.
        """
        fields = list(super().get_fields(request, obj))
        if obj is None:
            return fields
        for anchor, extra in (("client_code", "user_client_code"), ("pickup_point", "user_pickup_point")):
            if anchor not in fields:
                continue
            # Django дописывает read-only поля в конец списка — переставляем.
            if extra in fields:
                fields.remove(extra)
            fields.insert(fields.index(anchor) + 1, extra)
        return fields

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "pickup_point" and field is not None:
            field.help_text = (
                "Где посылку физически приняли. Пусто — ещё не принята; до приёмки "
                "она числится за ПВЗ клиента (см. строку ниже), и поиск по ПВЗ её "
                "находит. Заполняется автоматически при статусе «В ПВЗ»."
            )
        return field

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # ПВЗ не был ограничен ничем: в списке лежали пункты всех карго, и
        # посылке можно было молча назначить чужой.
        if db_field.name == "pickup_point":
            cargo_id = get_request_cargo_id(request.user)
            obj_id = request.resolver_match.kwargs.get("object_id") if request.resolver_match else None
            if obj_id:
                parcel = Parcel.objects.filter(pk=obj_id).only("cargo_id").first()
                if parcel is not None:
                    cargo_id = parcel.cargo_id
            if cargo_id:
                kwargs["queryset"] = PickupPoint.objects.filter(cargo_id=cargo_id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
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
