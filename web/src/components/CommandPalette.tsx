import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { allowedTabs, get, getRole } from '../api';
import { useI18n } from '../i18n';
import { useTheme } from '../theme';
import { NAV } from '../nav';
import { useDialog } from '../ui/useDialog';
import type { ClientHit } from './ClientSearch';
import {
  IconArrowUpDown,
  IconCornerDownLeft,
  IconGlobe,
  IconLogout,
  IconMonitor,
  IconMoon,
  IconSearch,
  IconStaff,
  IconSun,
  type IconProps,
} from './Icons';

type Item = {
  id: string;
  title: string;
  subtitle?: string;
  Icon: (p: IconProps) => JSX.Element;
  group: string;
  run: () => void;
};

/**
 * Командная палитра (Ctrl/⌘ + K): переход по разделам, поиск клиента и
 * быстрые действия. Открывается из топбара и с клавиатуры.
 */
export default function CommandPalette({
  onClose,
  onLogout,
}: {
  onClose: () => void;
  onLogout: () => void;
}) {
  const { t, lang, setLang } = useI18n();
  const { mode, setMode } = useTheme();
  const nav = useNavigate();
  const panelRef = useDialog<HTMLDivElement>({ onClose, autoFocus: false });
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const [q, setQ] = useState('');
  const [clients, setClients] = useState<ClientHit[]>([]);
  const [active, setActive] = useState(0);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Поиск клиентов — только менеджерам и от двух символов, чтобы не дёргать API
  // на каждую букву при обычной навигации по разделам.
  const canSearchClients = useMemo(() => {
    const role = getRole();
    return Boolean(role.is_superuser || role.is_cargo_admin || role.is_staff);
  }, []);

  useEffect(() => {
    const query = q.trim();
    if (!canSearchClients || query.length < 2) {
      setClients([]);
      return;
    }
    let cancelled = false;
    const h = setTimeout(() => {
      get(`/api/clients/search/?q=${encodeURIComponent(query)}`)
        .then((d: any) => !cancelled && setClients((d as ClientHit[]).slice(0, 5)))
        .catch(() => !cancelled && setClients([]));
    }, 220);
    return () => {
      cancelled = true;
      clearTimeout(h);
    };
  }, [q, canSearchClients]);

  const items = useMemo<Item[]>(() => {
    const tabs = allowedTabs();
    const go = (to: string) => () => {
      nav(to);
      onClose();
    };

    const pages: Item[] = NAV.flatMap((g) =>
      g.items
        .filter((i) => tabs.includes(i.tab))
        .map((i) => ({
          id: `nav:${i.to}`,
          title: t(i.label),
          subtitle: t(g.group),
          Icon: i.icon as Item['Icon'],
          group: t('cmdk.groupPages'),
          run: go(i.to),
        })),
    );
    pages.push({
      id: 'nav:/profile',
      title: t('nav.profile'),
      Icon: IconStaff,
      group: t('cmdk.groupPages'),
      run: go('/profile'),
    });

    const themeIcon = { auto: IconMonitor, light: IconSun, dark: IconMoon } as const;
    const actions: Item[] = [
      {
        id: 'act:theme',
        title: t('cmdk.theme'),
        subtitle: t(`theme.${mode}`),
        Icon: themeIcon[mode],
        group: t('cmdk.groupActions'),
        run: () => {
          setMode(mode === 'dark' ? 'light' : 'dark');
          onClose();
        },
      },
      {
        id: 'act:lang',
        title: t('cmdk.lang'),
        subtitle: lang === 'ru' ? '中文' : 'Русский',
        Icon: IconGlobe,
        group: t('cmdk.groupActions'),
        run: () => {
          setLang(lang === 'ru' ? 'zh' : 'ru');
          onClose();
        },
      },
      {
        id: 'act:logout',
        title: t('common.logout'),
        Icon: IconLogout,
        group: t('cmdk.groupActions'),
        run: () => {
          onClose();
          onLogout();
        },
      },
    ];

    const query = q.trim().toLowerCase();
    const match = (i: Item) =>
      !query || i.title.toLowerCase().includes(query) || (i.subtitle ?? '').toLowerCase().includes(query);

    const clientItems: Item[] = clients.map((c) => ({
      id: `client:${c.id}`,
      title: c.full_name || c.client_code,
      subtitle: [c.client_code, c.phone, c.pickup_point_title].filter(Boolean).join(' · '),
      Icon: IconStaff,
      group: t('cmdk.groupClients'),
      run: () => {
        nav(`/clients?q=${encodeURIComponent(c.client_code)}`);
        onClose();
      },
    }));

    return [...pages.filter(match), ...clientItems, ...actions.filter(match)];
  }, [q, clients, t, lang, setLang, mode, setMode, nav, onClose, onLogout]);

  // Сбрасываем курсор на первый пункт при смене выдачи.
  useEffect(() => setActive(0), [q, clients.length]);

  // Держим выделенный пункт в зоне видимости при навигации стрелками.
  useEffect(() => {
    listRef.current
      ?.querySelector<HTMLElement>('[aria-selected="true"]')
      ?.scrollIntoView({ block: 'nearest' });
  }, [active]);

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((i) => (items.length ? (i + 1) % items.length : 0));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((i) => (items.length ? (i - 1 + items.length) % items.length : 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      items[active]?.run();
    }
  }

  // Заголовок группы печатаем только при её смене — список идёт секциями.
  let lastGroup = '';

  return (
    <div className="cmdk-overlay" onMouseDown={onClose}>
      <div
        ref={panelRef}
        className="cmdk"
        role="dialog"
        aria-modal="true"
        aria-label={t('cmdk.title')}
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={onKeyDown}
      >
        <div className="cmdk-search">
          <IconSearch size={18} />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t('cmdk.placeholder')}
            aria-label={t('cmdk.placeholder')}
            autoComplete="off"
            spellCheck={false}
          />
        </div>

        <div className="cmdk-list" ref={listRef} role="listbox" aria-label={t('cmdk.title')}>
          {items.length === 0 ? (
            <div className="cmdk-empty">{t('cmdk.empty')}</div>
          ) : (
            items.map((item, i) => {
              const header = item.group !== lastGroup ? item.group : null;
              lastGroup = item.group;
              return (
                <div key={item.id}>
                  {header && <div className="cmdk-group">{header}</div>}
                  <button
                    type="button"
                    role="option"
                    aria-selected={i === active}
                    className="cmdk-item"
                    onMouseEnter={() => setActive(i)}
                    onClick={item.run}
                  >
                    <item.Icon size={17} />
                    <span className="cmdk-main">
                      <span className="cmdk-title">{item.title}</span>
                      {item.subtitle && <span className="cmdk-sub">{item.subtitle}</span>}
                    </span>
                  </button>
                </div>
              );
            })
          )}
        </div>

        <div className="cmdk-foot">
          <span>
            <IconArrowUpDown size={13} /> {t('cmdk.hintMove')}
          </span>
          <span>
            <IconCornerDownLeft size={13} /> {t('cmdk.hintOpen')}
          </span>
          <span>
            <kbd>Esc</kbd> {t('cmdk.hintClose')}
          </span>
        </div>
      </div>
    </div>
  );
}
