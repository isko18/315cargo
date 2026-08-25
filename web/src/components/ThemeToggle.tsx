import { useI18n } from '../i18n';
import { useTheme, type ThemeMode } from '../theme';
import { IconMonitor, IconMoon, IconSun } from './Icons';

const OPTIONS: { key: ThemeMode; Icon: typeof IconSun }[] = [
  { key: 'auto', Icon: IconMonitor },
  { key: 'light', Icon: IconSun },
  { key: 'dark', Icon: IconMoon },
];

/** Переключатель темы: авто (системная) / светлая / тёмная. */
export default function ThemeToggle() {
  const { mode, setMode } = useTheme();
  const { t } = useI18n();

  return (
    <div className="theme-switch" role="group" aria-label={t('theme.label')}>
      {OPTIONS.map(({ key, Icon }) => (
        <button
          key={key}
          type="button"
          className={mode === key ? 'active' : ''}
          aria-pressed={mode === key}
          title={t(`theme.${key}`)}
          aria-label={t(`theme.${key}`)}
          onClick={() => setMode(key)}
        >
          <Icon size={16} />
        </button>
      ))}
    </div>
  );
}
