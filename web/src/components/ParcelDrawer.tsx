import { useEffect, useState } from 'react';
import { money } from '../money';
import { ApiError, get } from '../api';
import { statusMeta } from '../status';
import { IconClose, IconBox } from './Icons';

export type Parcel = {
  id: number;
  track_number: string;
  client_code: string | null;
  client_name?: string | null;
  client_phone?: string | null;
  pickup_point_title?: string | null;
  status: string;
  status_display_name: string;
  product_title?: string | null;
  product_price?: string | number | null;
  product_image?: string | null;
  location?: string | null;
  weight: string | null;
  volume?: string | null;
  delivery_price: string | null;
  arrived_at?: string | null;
  issued_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

type HistoryItem = {
  id: number;
  status: string;
  status_display_name: string;
  comment: string;
  changed_by_phone: string | null;
  created_at: string;
};

const fmt = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleString('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }) : '—';

export default function ParcelDrawer({ parcel, onClose }: { parcel: Parcel; onClose: () => void }) {
  const [history, setHistory] = useState<HistoryItem[] | null>(null);
  const meta = statusMeta(parcel.status);

  useEffect(() => {
    setHistory(null);
    get<HistoryItem[]>(`/api/parcels/${parcel.id}/history/`)
      .then(setHistory)
      .catch((_: ApiError) => setHistory([]));
  }, [parcel.id]);

  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onEsc);
    return () => window.removeEventListener('keydown', onEsc);
  }, [onClose]);

  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label="Детали посылки">
        <div className="drawer-head">
          <span className="track mono">{parcel.track_number}</span>
          <span className={`badge tone-${meta.tone}`}>
            <span className="dot" />
            {meta.label}
          </span>
          <span className="spacer" />
          <button className="x" onClick={onClose} aria-label="Закрыть">
            <IconClose size={20} />
          </button>
        </div>

        <div className="drawer-body">
          <div className="drawer-hero">
            {parcel.product_image ? (
              <img src={parcel.product_image} alt="" />
            ) : (
              <span className="ph">
                <IconBox size={26} />
              </span>
            )}
            <div>
              <div className="t">{parcel.product_title || 'Товар не указан'}</div>
              <div className="p">
                {parcel.product_price ? `Цена товара: $${parcel.product_price}` : 'Цена товара не указана'}
              </div>
            </div>
          </div>

          <div className="detail-grid">
            <Cell k="Вес" v={parcel.weight ? `${parcel.weight} кг` : '—'} />
            <Cell k="Стоимость доставки" v={money(parcel.delivery_price)} />
            <Cell k="Клиент" v={parcel.client_name || '—'} />
            <Cell k="Код клиента" v={parcel.client_code || '—'} mono />
            <Cell k="Телефон" v={parcel.client_phone || '—'} mono />
            <Cell k="ПВЗ" v={parcel.pickup_point_title || '—'} />
            <Cell k="Местоположение" v={parcel.location || '—'} full />
            <Cell k="Принят на склад" v={fmt(parcel.arrived_at)} />
            <Cell k="Выдан" v={fmt(parcel.issued_at)} />
            <Cell k="Создан" v={fmt(parcel.created_at)} />
            <Cell k="Обновлён" v={fmt(parcel.updated_at)} />
          </div>

          <div className="section-title">История статусов</div>
          {history === null ? (
            <div className="timeline">
              {[0, 1].map((i) => (
                <div className="tl-item" key={i}>
                  <div className="skeleton" style={{ height: 14, width: '55%' }} />
                  <div className="skeleton" style={{ height: 11, width: '35%', marginTop: 6 }} />
                </div>
              ))}
            </div>
          ) : history.length === 0 ? (
            <p className="muted" style={{ fontSize: 13 }}>История пуста.</p>
          ) : (
            <div className="timeline">
              {history.map((h) => {
                const hm = statusMeta(h.status);
                return (
                  <div className={`tl-item tone-${hm.tone}`} key={h.id}>
                    <div className="tl-status">{hm.label}</div>
                    <div className="tl-meta">
                      {fmt(h.created_at)}
                      {h.changed_by_phone ? ` · ${h.changed_by_phone}` : ''}
                    </div>
                    {h.comment && <div className="tl-comment">{h.comment}</div>}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}

function Cell({ k, v, mono, full }: { k: string; v: string; mono?: boolean; full?: boolean }) {
  return (
    <div className={`detail-cell ${full ? 'full' : ''}`}>
      <div className="k">{k}</div>
      <div className={`v ${mono ? 'mono' : ''}`}>{v}</div>
    </div>
  );
}
