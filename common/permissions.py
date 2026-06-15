from rest_framework.permissions import SAFE_METHODS, BasePermission

from .cargo_scoping import user_is_cargo_manager


class IsOwnerOrStaff(BasePermission):
    def has_object_permission(self, request, view, obj):
        if user_is_cargo_manager(request.user):
            if request.user.is_superuser or not request.user.cargo_id:
                return True
            owner = getattr(obj, "user", None)
            if owner is not None:
                return owner.cargo_id == request.user.cargo_id
            if hasattr(obj, "cargo_id"):
                return obj.cargo_id == request.user.cargo_id
            return obj == request.user
        owner = getattr(obj, "user", None)
        if owner is not None:
            return owner == request.user
        return obj == request.user


class IsStaffOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return user_is_cargo_manager(request.user)


class IsCargoManager(BasePermission):
    """Владелец/админ карго (или staff/superuser) — операции управления."""

    def has_permission(self, request, view):
        return user_is_cargo_manager(request.user)


class IsSuperOwner(BasePermission):
    """Главный владелец — глобальный суперпользователь."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_superuser)
