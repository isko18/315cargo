"""Вкладки панели и доступ к ним по ролям.

Единый источник правды: ключи вкладок совпадают с маршрутами React-панели.
Владелец карго выдаёт оператору доступ к конкретным вкладкам.
"""

# Все вкладки панели.
TABS = (
    "scan",            # Приём
    "issue",           # Выдача
    "warehouse",       # Склад
    "china",           # Склад в Китае
    "clients",         # Клиенты
    "delivery",        # Заявки на доставку
    "staff",           # Сотрудники
    "pickup",          # Пункты выдачи
    "tariff",          # Настройки карго: тариф приёмки + формат кода клиента
    "delivery_tariff",  # Тариф доставки по городу
    "analytics",       # Аналитика
    "overview",        # Все карго (только супер-владелец)
    "delivery_address",  # Адрес доставки Китай/PDD (только супер-владелец)
)

# Что владелец/админ карго может выдавать обычному оператору.
GRANTABLE_TABS = (
    "scan",
    "issue",
    "warehouse",
    "clients",
    "delivery",
    "staff",
    "pickup",
    "tariff",
    "delivery_tariff",
    "analytics",
)

# Базовый набор для нового оператора, если явно ничего не выбрано.
DEFAULT_OPERATOR_TABS = ("scan", "issue", "warehouse")

# Полный набор для админа карго. Склад Китая (china) — только у супер-владельца
# и china-операторов; overview — только у супер-владельца.
CARGO_ADMIN_TABS = (
    "scan",
    "issue",
    "warehouse",
    "clients",
    "delivery",
    "staff",
    "pickup",
    "tariff",
    "delivery_tariff",
    "analytics",
)


def user_allowed_tabs(user):
    """Список вкладок, доступных пользователю (по роли + персональному списку)."""
    if not user or not user.is_authenticated:
        return []
    if user.is_superuser:
        return list(TABS)
    if getattr(user, "is_cargo_admin", False):
        return list(CARGO_ADMIN_TABS)
    if getattr(user, "is_china_staff", False):
        return ["china"]
    granted = [t for t in (user.allowed_tabs or []) if t in GRANTABLE_TABS]
    return granted


def sanitize_tabs(values):
    """Оставить только валидные выдаваемые вкладки, сохранив порядок TABS."""
    requested = set(values or [])
    return [t for t in TABS if t in requested and t in GRANTABLE_TABS]
