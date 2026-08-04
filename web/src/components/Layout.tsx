import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { clearToken, clearRefresh, clearRole, get, getRole, isChinaOnly, isPickupBound, allowedTabs, setRole, type ApiError } from '../api';
import { PickupProvider, usePickup } from '../pickupContext';
import { useI18n } from '../i18n';
import LangSwitcher from './LangSwitcher';
import AlertsBell from './AlertsBell';
import {
  IconScan,
  IconIssue,
  IconWarehouse,
  IconGlobe,
  IconStaff,
  IconTariff,
  IconAnalytics,
  IconOverview,
  IconTruck,
  IconRevenue,
  IconPin,
  IconLogout,
  IconMenu,
  IconClose,
  IconSidebar,
} from './Icons';

const NAV = [
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
      { to: '/tariff', tab: 'tariff', label: 'nav.tariff', icon: IconTariff },
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

const TITLES: Record<string, string> = Object.fromEntries(
  NAV.flatMap((g) => g.items).map((i) => [i.to, i.label]),
);

export default function Layout() {
  return (
    <PickupProvider>
      <LayoutInner />
    </PickupProvider>
  );
}

function PickupSwitcher() {
  const { points, activeId, setActiveId } = usePickup();
  // Привязанный оператор работает в одном ПВЗ — переключатель ему не нужен.
  if (isChinaOnly() || isPickupBound() || points.length === 0) return null;
  return (
    <select
      className="pvz-switch"
      value={activeId ?? ''}
      onChange={(e) => setActiveId(e.target.value ? Number(e.target.value) : null)}
      aria-label="Активный ПВЗ"
      title="Активный пункт выдачи"
    >
      <option value="">Все ПВЗ</option>
      {points.map((p) => (
        <option key={p.id} value={p.id}>
          {p.title}
        </option>
      ))}
    </select>
  );
}

function LayoutInner() {
  const nav = useNavigate();
  const loc = useLocation();
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  // Свёрнутый сайдбар (десктоп): узкий rail только с иконками. Сохраняем выбор.
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('nav-collapsed') === '1');
  const [, setTick] = useState(0);

  function toggleCollapsed() {
    setCollapsed((v) => {
      const next = !v;
      localStorage.setItem('nav-collapsed', next ? '1' : '0');
      return next;
    });
  }

  // Тихое обновление роли при загрузке панели: если владелец изменил доступы,
  // оператор получит их после обычного refresh, без перезахода.
  useEffect(() => {
    get('/api/profile/')
      .then((u: any) => {
        setRole({
          is_china_staff: u.is_china_staff,
          is_cargo_admin: u.is_cargo_admin,
          is_superuser: u.is_superuser,
          is_staff: u.is_staff,
          allowed_tabs: u.allowed_tabs,
          pickup_point: u.pickup_point ?? null,
        });
        if (u.full_name || u.phone) localStorage.setItem('who', u.full_name || u.phone);
        setTick((n) => n + 1);
      })
      .catch((e: ApiError) => {
        if (e?.status === 401) {
          clearToken();
          clearRole();
          nav('/login', { replace: true });
        }
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const who = localStorage.getItem('who') || 'Оператор';
  const role = getRole();
  const chinaOnly = isChinaOnly(role);
  const roleLabel = chinaOnly
    ? t('roles.china')
    : role.is_superuser
      ? t('roles.owner')
      : role.is_cargo_admin
        ? t('roles.cargoAdmin')
        : t('roles.staff');
  const initials = who
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase();

  // Меню фильтруется по эффективным правам вкладок (роль + персональный список).
  const tabs = allowedTabs(role);
  const visibleNav = NAV.map((g) => ({
    ...g,
    items: g.items.filter((i) => tabs.includes(i.tab)),
  })).filter((g) => g.items.length > 0);

  function logout() {
    clearToken();
    clearRefresh();
    clearRole();
    localStorage.removeItem('who');
    nav('/login', { replace: true });
  }

  const pageTitle =
    TITLES[loc.pathname] || (loc.pathname === '/profile' ? 'nav.profile' : '315CARGO');

  return (
    <div className={`shell ${collapsed ? 'nav-collapsed' : ''}`}>
      <div className={`scrim ${open ? 'show' : ''}`} onClick={() => setOpen(false)} />

      <aside className={`sidebar ${open ? 'open' : ''}`}>
        <div className="brand">
          <div className="mark">315</div>
          <div className="name">
            315CARGO
            <small>ADMIN PANEL</small>
          </div>
        </div>

        <div className="nav-scroll">
          {visibleNav.map((g) => (
            <div key={g.group} className="nav-group">
              <div className="nav-group-label">{t(g.group)}</div>
              <nav>
                {g.items.map(({ to, label, icon: Icon }) => (
                  <NavLink
                    key={to}
                    to={to}
                    onClick={() => setOpen(false)}
                    title={t(label)}
                    className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                  >
                    <Icon size={19} />
                    <span className="nav-label">{t(label)}</span>
                  </NavLink>
                ))}
              </nav>
            </div>
          ))}
        </div>

        <div className="side-user">
          <NavLink
            to="/profile"
            onClick={() => setOpen(false)}
            className="side-user-link"
            title={t('nav.profile')}
          >
            <div className="avatar">{initials || 'OP'}</div>
            <div className="meta">
              <div className="nm">{who}</div>
              <div className="rl">{roleLabel}</div>
            </div>
          </NavLink>
          <button className="logout" onClick={logout} aria-label={t('common.logout')} title={t('common.logout')}>
            <IconLogout size={18} />
          </button>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <button className="menu-btn" onClick={() => setOpen((v) => !v)} aria-label={t('common.menu')}>
            {open ? <IconClose size={22} /> : <IconMenu size={22} />}
          </button>
          <button
            className="collapse-btn"
            onClick={toggleCollapsed}
            aria-label={t('common.toggleNav')}
            title={t('common.toggleNav')}
            aria-pressed={collapsed}
          >
            <IconSidebar size={20} />
          </button>
          <span className="page-title">{t(pageTitle)}</span>
          <span className="spacer" />
          {tabs.includes('warehouse') && <AlertsBell />}
          <PickupSwitcher />
          <LangSwitcher />
          <span className="env-pill">{t('common.online')}</span>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
