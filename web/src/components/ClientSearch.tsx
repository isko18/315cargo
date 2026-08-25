import { useEffect, useId, useRef, useState } from 'react';
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
 *
 * Разметка комбобокса (role=combobox + listbox + aria-activedescendant) и
 * стрелки ↑/↓ — оператору быстрее выбрать клиента, не снимая рук с клавиатуры.
 */
export default function ClientSearch({
  onPick,
  placeholder,
  autoFocus,
  size = 'md',
  initialQuery = '',
}: {
  onPick: (c: ClientHit) => void;
  placeholder?: string;
  autoFocus?: boolean;
  size?: 'md' | 'sm';
  /** Стартовое значение поля (например, код из QR). Меняется через key-ремоунт. */
  initialQuery?: string;
}) {
  const { t } = useI18n();
  const [q, setQ] = useState(initialQuery);
  const [debounced, setDebounced] = useState('');
  const [results, setResults] = useState<ClientHit[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [rect, setRect] = useState<{ top: number; left: number; width: number } | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const listId = useId();

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
          setActive(0);
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
  const hits = results ?? [];

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (!hits.length) return;
      e.preventDefault();
      setOpen(true);
      setActive((i) => (e.key === 'ArrowDown' ? (i + 1) % hits.length : (i - 1 + hits.length) % hits.length));
      return;
    }
    if (e.key === 'Enter') {
      const hit = open && hits[active] ? hits[active] : hits.length === 1 ? hits[0] : null;
      if (hit) {
        e.preventDefault();
        pick(hit);
      }
      return;
    }
    if (e.key === 'Escape') setOpen(false);
  }

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
        onKeyDown={onKeyDown}
        placeholder={placeholder ?? t('clientsearch.placeholder')}
        autoComplete="off"
        spellCheck={false}
        autoFocus={autoFocus}
        role="combobox"
        aria-expanded={Boolean(showMenu)}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={showMenu && hits[active] ? `${listId}-${hits[active].id}` : undefined}
      />
      {showMenu && (
        <div
          className="cs-menu"
          id={listId}
          role="listbox"
          aria-label={t('clientsearch.results')}
          style={{ position: 'fixed', top: rect!.top, left: rect!.left, width: rect!.width }}
        >
          {loading && !results ? (
            <div className="cs-empty">{t('common.loading')}</div>
          ) : hits.length ? (
            hits.map((c, i) => (
              <button
                type="button"
                key={c.id}
                id={`${listId}-${c.id}`}
                role="option"
                aria-selected={i === active}
                className={`cs-item ${i === active ? 'is-active' : ''}`}
                onMouseEnter={() => setActive(i)}
                onClick={() => pick(c)}
              >
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
