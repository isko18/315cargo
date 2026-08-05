// Единый источник правды по вкладкам панели (зеркалит common/tabs.py).

export const TAB_LABELS: Record<string, string> = {
  scan: 'Приём',
  issue: 'Выдача',
  warehouse: 'Склад',
  china: 'Склад Китай',
  clients: 'Клиенты',
  delivery: 'Заявки на доставку',
  staff: 'Сотрудники',
  pickup: 'Пункты выдачи',
  tariff: 'Настройки карго',
  delivery_tariff: 'Тариф доставки',
  analytics: 'Аналитика',
  overview: 'Все карго',
  delivery_address: 'Адрес доставки',
};

// Что владелец может выдавать обычному оператору.
export const GRANTABLE_TABS = [
  'scan',
  'issue',
  'warehouse',
  'clients',
  'delivery',
  'staff',
  'pickup',
  'tariff',
  'delivery_tariff',
  'analytics',
];

// Базовый набор для нового оператора.
export const DEFAULT_OPERATOR_TABS = ['scan', 'issue', 'warehouse'];

// Маршрут → ключ вкладки.
export const ROUTE_TAB: Record<string, string> = {
  '/scan': 'scan',
  '/issue': 'issue',
  '/warehouse': 'warehouse',
  '/china': 'china',
  '/clients': 'clients',
  '/delivery': 'delivery',
  '/staff': 'staff',
  '/pickup-points': 'pickup',
  '/cargo-settings': 'tariff',
  '/delivery-tariff': 'delivery_tariff',
  '/analytics': 'analytics',
  '/overview': 'overview',
  '/delivery-address': 'delivery_address',
};

export const TAB_ROUTE: Record<string, string> = Object.fromEntries(
  Object.entries(ROUTE_TAB).map(([route, tab]) => [tab, route]),
);
