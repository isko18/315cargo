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


def filter_owned_queryset(queryset, user, owner_lookup="user"):
    if not user or not user.is_authenticated:
        return queryset.none()
    if user_is_cargo_manager(user):
        cargo_id = get_request_cargo_id(user)
        if cargo_id:
            return queryset.filter(**{f"{owner_lookup}__cargo_id": cargo_id})
        return queryset
    return queryset.filter(**{owner_lookup: user})
