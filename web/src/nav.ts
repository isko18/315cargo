import type { ComponentType, SVGProps } from 'react';
import {
  IconAnalytics,
  IconGlobe,
  IconIssue,
  IconOverview,
  IconPin,
  IconRevenue,
  IconScan,
  IconStaff,
  IconTariff,
  IconTruck,
  IconWarehouse,
} from './components/Icons';

export type NavIcon = ComponentType<SVGProps<SVGSVGElement> & { size?: number }>;

export interface NavItem {
  to: string;
  tab: string;
  /** Ключ i18n. */
  label: string;
  icon: NavIcon;
}

export interface NavGroup {
  /** Ключ i18n. */
  group: string;
  items: NavItem[];
}

/** Разделы панели. Общий источник для сайдбара и командной палитры. */
export const NAV: NavGroup[] = [
  {
    group: 'nav.group.ops',
    items: [
      { to: '/scan', tab: 'scan', label: 'nav.scan', icon: IconScan },
      { to: '/issue', tab: 'issue', label: 'nav.issue', icon: IconIssue },
      { to: '/warehouse', tab: 'warehouse', label: 'nav.warehouse', icon: IconWarehouse },
      { to: '/china', tab: 'china', label: 'nav.china', icon: IconGlobe },
    ],
  },
  {
    group: 'nav.group.clients',
    items: [
      { to: '/clients', tab: 'clients', label: 'nav.clients', icon: IconStaff },
      { to: '/delivery', tab: 'delivery', label: 'nav.delivery', icon: IconTruck },
    ],
  },
  {
    group: 'nav.group.manage',
    items: [
      { to: '/staff', tab: 'staff', label: 'nav.staff', icon: IconStaff },
      { to: '/pickup-points', tab: 'pickup', label: 'nav.pickup', icon: IconWarehouse },
      { to: '/cargo-settings', tab: 'tariff', label: 'nav.cargoSettings', icon: IconTariff },
      { to: '/delivery-tariff', tab: 'delivery_tariff', label: 'nav.deliveryTariff', icon: IconRevenue },
      { to: '/delivery-address', tab: 'delivery_address', label: 'nav.deliveryAddress', icon: IconPin },
    ],
  },
  {
    group: 'nav.group.analytics',
    items: [
      { to: '/analytics', tab: 'analytics', label: 'nav.analytics', icon: IconAnalytics },
      { to: '/overview', tab: 'overview', label: 'nav.overview', icon: IconOverview },
    ],
  },
];

/** Ключ i18n заголовка страницы по её пути. */
export const NAV_TITLES: Record<string, string> = Object.fromEntries(
  NAV.flatMap((g) => g.items).map((i) => [i.to, i.label]),
);
