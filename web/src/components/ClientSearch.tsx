import { useEffect, useRef, useState } from 'react';
import { get } from '../api';
import { useI18n } from '../i18n';
import { IconSearch } from './Icons';
import { Input } from '../ui';

export type ClientHit = {
  id: number;
  full_name: string;
  phone: string;
  client_code: string;
  pickup_point_title: string | null;
};

/**
 * Живой поиск клиента: печатаешь имя/телефон/код → выпадающий список → выбор.
 * Меню position: fixed, чтобы не обрезалось внутри таблиц/карточек.
 */
export default function ClientSearch({
  onPick,
  placeholder,
  autoFocus,
  size = 'md',
}: {
  onPick: (c: ClientHit) => void;
  placeholder?: string;
  autoFocus?: boolean;
  size?: 'md' | 'sm';
}) {
  const { t } = useI18n();
  const [q, setQ] = useState('');
  const [debounced, setDebounced] = useState('');
  const [results, setResults] = useState<ClientHit[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [rect, setRect] = useState<{ top: number; left: number; width: number } | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const h = setTimeout(() => setDebounced(q.trim()), 250);
    return () => clearTimeout(h);
  }, [q]);

  useEffect(() => {
    if (debounced.length < 1) {
      setResults(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    get(`/api/clients/search/?q=${encodeURIComponent(debounced)}`)
      .then((d: any) => {
        if (!cancelled) {
          setResults(d as ClientHit[]);
          setOpen(true);
        }
      })
      .catch(() => !cancelled && setResults([]))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [debounced]);

  // Позиция меню (fixed) под инпутом; обновляем на скролл/ресайз.
  useEffect(() => {
    if (!open) return;
    const update = () => {
      const el = wrapRef.current?.querySelector('input');
      if (el) {
        const r = el.getBoundingClientRect();
        setRect({ top: r.bottom + 4, left: r.left, width: r.width });
      }
    };
    update();
    window.addEventListener('scroll', update, true);
    window.addEventListener('resize', update);
    return () => {
      window.removeEventListener('scroll', update, true);
      window.removeEventListener('resize', update);
    };
  }, [open, results]);

  // Закрытие по клику вне.
  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  function pick(c: ClientHit) {
    onPick(c);
    setQ(c.full_name || c.client_code);
    setOpen(false);
  }

  const showMenu = open && debounced.length >= 1 && rect;

  return (
    <div className={`client-search ${size === 'sm' ? 'cs-sm' : ''}`} ref={wrapRef}>
      <Input
        icon={<IconSearch size={size === 'sm' ? 16 : 18} />}
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => results && setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && results && results.length === 1) {
            e.preventDefault();
            pick(results[0]);
          } else if (e.key === 'Escape') {
            setOpen(false);
          }
        }}
        placeholder={placeholder ?? t('clientsearch.placeholder')}
        autoComplete="off"
        autoFocus={autoFocus}
      />
      {showMenu && (
        <div
          className="cs-menu"
          style={{ position: 'fixed', top: rect!.top, left: rect!.left, width: rect!.width }}
        >
          {loading && !results ? (
            <div className="cs-empty">{t('common.loading')}</div>
          ) : results && results.length ? (
            results.map((c) => (
              <button type="button" key={c.id} className="cs-item" onClick={() => pick(c)}>
                <span className="cs-name">{c.full_name || '—'}</span>
                <span className="cs-meta">
                  <span className="mono">{c.client_code}</span>
                  <span className="cs-phone">{c.phone}</span>
                  {c.pickup_point_title && <span className="cs-pp">{c.pickup_point_title}</span>}
                </span>
              </button>
            ))
          ) : (
            <div className="cs-empty">{t('clientsearch.none')}</div>
          )}
        </div>
      )}
    </div>
  );
}
