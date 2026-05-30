from django.contrib import admin

from cargo.models import CargoCompany

from .cargo_scoping import get_request_cargo_id, user_is_cargo_manager


class CargoScopedAdminMixin:
    cargo_field = "cargo"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        cargo_id = get_request_cargo_id(request.user)
        if cargo_id and user_is_cargo_manager(request.user):
            return qs.filter(**{self.cargo_field: cargo_id})
        return qs.none()

    def has_module_permission(self, request):
        if request.user.is_superuser:
            return True
        cargo_id = get_request_cargo_id(request.user)
        if cargo_id and user_is_cargo_manager(request.user):
            return True
        return super().has_module_permission(request)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        cargo_id = get_request_cargo_id(request.user)
        if (
            db_field.name == self.cargo_field
            and not request.user.is_superuser
            and cargo_id
        ):
            kwargs["queryset"] = CargoCompany.objects.filter(pk=cargo_id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        cargo_id = get_request_cargo_id(request.user)
        if (
            not change
            and not request.user.is_superuser
            and cargo_id
            and hasattr(obj, self.cargo_field)
        ):
            setattr(obj, self.cargo_field, request.user.cargo)
        super().save_model(request, obj, form, change)
