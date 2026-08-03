import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { get } from '../api';
import { IconAlert, IconBox } from './Icons';

type Pending = {
  id: number;
  track_number: string;
  created_at?: string | null;
  product_title?: string | null;
};

const fmt = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' }) : '';

/**
 * Индикатор «требуют внимания» для операторов: посылки без клиента (pending)
 * по своему карго. Клиент-уведомления (заказы/статусы) адресованы клиентам,
 * поэтому в панели показываем то, что требует действия сотрудника.
 */
export default function AlertsBell() {
  const nav = useNavigate();
  const [items, setItems] = useState<Pending[]>([]);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  function load() {
    get('/api/parcels/?pending=true')
      .then((d: any) => setItems(((d?.results ?? d) as Pending[]).slice(0, 8)))
      .catch(() => setItems([]));
  }

  useEffect(() => {
    load();
    const id = window.setInterval(load, 60_000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (open && ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const count = items.length;

  return (
    <div className="bell-wrap" ref={ref}>
      <button
        className="bell"
        onClick={() => {
          if (!open) load();
          setOpen((v) => !v);
        }}
        aria-label="Требуют внимания"
        title="Посылки без клиента"
      >
        <IconAlert size={19} />
        {count > 0 && <span className="bell-badge">{count > 8 ? '8+' : count}</span>}
      </button>

      {open && (
        <div className="popover">
          <div className="popover-head">Требуют привязки к клиенту</div>
          {items.length === 0 ? (
            <div className="popover-empty">Нет посылок без клиента 🎉</div>
          ) : (
            <>
              <div className="popover-list">
                {items.map((p) => (
                  <div className="popover-item" key={p.id}>
                    <span className="pi-ico"><IconBox size={16} /></span>
                    <div className="grow" style={{ minWidth: 0 }}>
                      <div className="mono strong truncate" style={{ fontSize: 13 }}>{p.track_number}</div>
                      <div className="muted truncate" style={{ fontSize: 12 }}>{p.product_title || 'товар не указан'}</div>
                    </div>
                    <span className="muted" style={{ fontSize: 11.5 }}>{fmt(p.created_at)}</span>
                  </div>
                ))}
              </div>
              <button
                className="popover-foot"
                onClick={() => {
                  setOpen(false);
                  nav('/warehouse');
                }}
              >
                Открыть склад →
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
