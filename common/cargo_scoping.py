def user_is_cargo_manager(user):
    if not user or not user.is_authenticated:
        return False
    return user.is_staff or getattr(user, "is_cargo_admin", False)


def get_request_cargo_id(user):
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser:
        return None
    return user.cargo_id


def filter_queryset_by_cargo(queryset, user, lookup="cargo"):
    cargo_id = get_request_cargo_id(user)
    if cargo_id:
        return queryset.filter(**{lookup: cargo_id})
    return queryset


def filter_owned_queryset(queryset, user, owner_lookup="user", cargo_lookup=None):
    """Scope ``queryset`` to what ``user`` may see.

    ``cargo_lookup`` лучше задавать для моделей с прямым FK на карго и
    возможным ``user=null`` (например, pending-посылки сканера): менеджер тогда
    видит записи и по владельцу, и по прямому карго. Клиент всегда видит только
    свои записи (записи без владельца ему недоступны).
    """
    from django.db.models import Q

    if not user or not user.is_authenticated:
        return queryset.none()
    if user_is_cargo_manager(user):
        cargo_id = get_request_cargo_id(user)
        if cargo_id:
            condition = Q(**{f"{owner_lookup}__cargo_id": cargo_id})
            if cargo_lookup:
                condition |= Q(**{f"{cargo_lookup}_id": cargo_id})
            return queryset.filter(condition)
        return queryset
    return queryset.filter(**{owner_lookup: user})
