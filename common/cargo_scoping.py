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


def bound_pickup_id(user):
    """ПВЗ, к которому жёстко привязан оператор (иначе None).

    Обычный сотрудник с назначенным ПВЗ (не админ карго / не супер / не
    оператор Китая) видит данные только своего пункта выдачи.
    """
    if not user or not user.is_authenticated:
        return None
    if (
        getattr(user, "is_staff", False)
        and not user.is_superuser
        and not getattr(user, "is_cargo_admin", False)
        and not getattr(user, "is_china_staff", False)
    ):
        return getattr(user, "pickup_point_id", None)
    return None


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
