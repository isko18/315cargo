import { useCallback, useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { clearToken, clearRefresh, clearRole, get, getRole, isChinaOnly, isPickupBound, allowedTabs, setRole, type ApiError } from '../api';
import { PickupProvider, usePickup } from '../pickupContext';
import { useI18n } from '../i18n';
import { NAV, NAV_TITLES } from '../nav';
import LangSwitcher from './LangSwitcher';
import ThemeToggle from './ThemeToggle';
import AlertsBell from './AlertsBell';
import CommandPalette from './CommandPalette';
import BottomNav from './BottomNav';
import { IconLogout, IconMenu, IconClose, IconSidebar, IconSearch } from './Icons';

export default function Layout() {
  return (
    <PickupProvider>
      <LayoutInner />
    </PickupProvider>
  );
}

function PickupSwitcher() {
  const { points, activeId, setActiveId } = usePickup();
  const { t } = useI18n();
  // Привязанный оператор работает в одном ПВЗ — переключатель ему не нужен.
  if (isChinaOnly() || isPickupBound() || points.length === 0) return null;
  return (
    <select
      className="pvz-switch"
      value={activeId ?? ''}
      onChange={(e) => setActiveId(e.target.value ? Number(e.target.value) : null)}
      aria-label={t('common.activePickup')}
      title={t('common.activePickup')}
    >
      <option value="">{t('common.allPickups')}</option>
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
  const [palette, setPalette] = useState(false);
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

  const logout = useCallback(() => {
    clearToken();
    clearRefresh();
    clearRole();
    localStorage.removeItem('who');
    nav('/login', { replace: true });
  }, [nav]);

  // Ctrl/⌘ + K — командная палитра из любого места панели.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setPalette((v) => !v);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Мобильное меню — модальный слой: закрываем его при переходе на страницу.
  useEffect(() => setOpen(false), [loc.pathname]);

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

  const pageTitle =
    NAV_TITLES[loc.pathname] || (loc.pathname === '/profile' ? 'nav.profile' : '315CARGO');

  return (
    <div className={`shell ${collapsed ? 'nav-collapsed' : ''}`}>
      <a className="skip-link" href="#main">
        {t('common.skipToContent')}
      </a>
      <div className={`scrim ${open ? 'show' : ''}`} onClick={() => setOpen(false)} />

      <aside className={`sidebar ${open ? 'open' : ''}`} aria-label={t('common.mainNav')}>
        <div className="brand">
          <div className="mark" aria-hidden="true">315</div>
          <div className="name" translate="no">
            315CARGO
            <small>ADMIN PANEL</small>
          </div>
        </div>

        <div className="nav-scroll">
          {visibleNav.map((g) => (
            <div key={g.group} className="nav-group">
              <div className="nav-group-label" id={`navg-${g.group}`}>
                {t(g.group)}
              </div>
              <nav aria-labelledby={`navg-${g.group}`}>
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

        {/* На телефоне топбар не вмещает переключатели — они живут здесь. */}
        <div className="side-tools">
          <PickupSwitcher />
          <div className="cluster gap-sm">
            <ThemeToggle />
            <LangSwitcher />
          </div>
        </div>

        <div className="side-user">
          <NavLink to="/profile" onClick={() => setOpen(false)} className="side-user-link" title={t('nav.profile')}>
            <div className="avatar" aria-hidden="true">{initials || 'OP'}</div>
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
          <button
            className="menu-btn"
            onClick={() => setOpen((v) => !v)}
            aria-label={t('common.menu')}
            aria-expanded={open}
          >
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
          {/* Не заголовок: настоящий h1 страницы живёт в PageHeader. */}
          <span className="page-title">{t(pageTitle)}</span>
          <span className="spacer" />
          <button
            type="button"
            className="cmdk-trigger"
            onClick={() => setPalette(true)}
            aria-label={t('cmdk.title')}
            aria-keyshortcuts="Control+K Meta+K"
          >
            <IconSearch size={16} />
            <span className="k">{t('cmdk.trigger')}</span>
            <kbd>Ctrl&nbsp;K</kbd>
          </button>
          {tabs.includes('warehouse') && <AlertsBell />}
          <PickupSwitcher />
          <ThemeToggle />
          <LangSwitcher />
          <span className="env-pill">{t('common.online')}</span>
        </header>
        <main className="content" id="main" tabIndex={-1}>
          <Outlet />
        </main>
      </div>

      <BottomNav onMore={() => setOpen(true)} />

      {palette && <CommandPalette onClose={() => setPalette(false)} onLogout={logout} />}
    </div>
  );
}
