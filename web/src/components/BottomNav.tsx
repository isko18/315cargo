import { NavLink } from 'react-router-dom';
import { allowedTabs, getRole } from '../api';
import { useI18n } from '../i18n';
import { NAV, type NavItem } from '../nav';
import { IconMenu } from './Icons';

/**
 * Нижняя панель навигации — только на телефоне. Операторы работают стоя, с
 * одной руки: три основных раздела попадают под большой палец, всё остальное
 * остаётся в боковом меню за кнопкой «Ещё».
 *
 * Порядок фиксированный (по частоте работы), а не по порядку меню.
 */
const PRIORITY = ['scan', 'issue', 'warehouse', 'china', 'clients', 'delivery'];

const ALL_ITEMS: NavItem[] = NAV.flatMap((g) => g.items);

export default function BottomNav({ onMore }: { onMore: () => void }) {
  const { t } = useI18n();
  const tabs = allowedTabs(getRole());

  const items = PRIORITY.map((tab) => ALL_ITEMS.find((i) => i.tab === tab))
    .filter((i): i is NavItem => Boolean(i) && tabs.includes(i!.tab))
    .slice(0, 3);

  // Одинокая вкладка не стоит целой панели — бургера хватит.
  if (items.length < 2) return null;

  return (
    <nav className="bottom-nav" aria-label={t('common.mainNav')}>
      {items.map(({ to, label, icon: Icon }) => (
        <NavLink key={to} to={to} className={({ isActive }) => `bn-item ${isActive ? 'active' : ''}`}>
          <Icon size={21} />
          <span className="bn-label">{t(label)}</span>
        </NavLink>
      ))}
      <button type="button" className="bn-item" onClick={onMore}>
        <IconMenu size={21} />
        <span className="bn-label">{t('common.more')}</span>
      </button>
    </nav>
  );
}
