import { useI18n, type Lang } from '../i18n';

export default function LangSwitcher() {
  const { lang, setLang } = useI18n();
  const opts: { key: Lang; label: string }[] = [
    { key: 'ru', label: 'RU' },
    { key: 'zh', label: '中文' },
  ];
  return (
    <div className="lang-switch" role="group" aria-label="Language">
      {opts.map((o) => (
        <button
          key={o.key}
          type="button"
          className={lang === o.key ? 'active' : ''}
          onClick={() => setLang(o.key)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
