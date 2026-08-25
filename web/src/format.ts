import type { Lang } from './i18n';

/**
 * Форматирование дат и чисел по текущему языку панели. Раньше локаль была
 * зашита как 'ru-RU' — китайский интерфейс всё равно показывал русские даты.
 */
const LOCALE: Record<Lang, string> = { ru: 'ru-RU', zh: 'zh-CN' };

export function localeOf(lang: Lang): string {
  return LOCALE[lang] ?? 'ru-RU';
}

// Intl.DateTimeFormat дорогой в конструировании — кешируем по локали и опциям.
const cache = new Map<string, Intl.DateTimeFormat>();

function formatter(lang: Lang, opts: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = `${lang}|${JSON.stringify(opts)}`;
  let f = cache.get(key);
  if (!f) {
    f = new Intl.DateTimeFormat(localeOf(lang), opts);
    cache.set(key, f);
  }
  return f;
}

/** Короткая дата: 05.08.26 */
export function fmtDate(iso: string | null | undefined, lang: Lang, fallback = '—'): string {
  if (!iso) return fallback;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return fallback;
  return formatter(lang, { day: '2-digit', month: '2-digit', year: '2-digit' }).format(d);
}

/** День и месяц без года — для компактных списков (колокольчик). */
export function fmtDayMonth(iso: string | null | undefined, lang: Lang, fallback = ''): string {
  if (!iso) return fallback;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return fallback;
  return formatter(lang, { day: '2-digit', month: '2-digit' }).format(d);
}

/** Дата и время: 5 авг. 2026 г., 14:03 */
export function fmtDateTime(iso: string | null | undefined, lang: Lang, fallback = '—'): string {
  if (!iso) return fallback;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return fallback;
  return formatter(lang, { dateStyle: 'medium', timeStyle: 'short' }).format(d);
}

/** Компактные дата+время для таблиц истории: 05.08, 14:03 */
export function fmtShortDateTime(iso: string | null | undefined, lang: Lang, fallback = '—'): string {
  if (!iso) return fallback;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return fallback;
  return formatter(lang, {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(d);
}
