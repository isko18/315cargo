import { useEffect, useState } from 'react';
import { ApiError, get } from '../api';
import { statusMeta } from '../status';
import { useI18n } from '../i18n';
import { IconSearch, IconStaff, IconBox, IconClose } from '../components/Icons';
import {
  Alert,
  Badge,
  Card,
  CardHeader,
  Column,
  DataTable,
  EmptyState,
  Field,
  Input,
  PageHeader,
} from '../ui';

type Client = {
  id: number;
  full_name: string;
  phone: string;
  client_code: string | null;
  pickup_point_title: string | null;
  orders_count: number;
  parcels_count: number;
  created_at: string;
};

type Order = {
  id: number;
  product_title: string;
  price: string | null;
  quantity: number;
  status_display_name: string;
  track_number: string;
  created_at: string;
};
type ParcelRow = {
  id: number;
  track_number: string;
  status: string;
  weight: string | null;
  delivery_price: string | null;
  created_at: string;
};
type History = {
  client: { full_name: string; phone: string; client_code: string | null; pickup_point_title: string | null };
  orders: Order[];
  parcels: ParcelRow[];
};

const fmtDate = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' }) : '—';

export default function ClientsPage() {
  const { t } = useI18n();
  const [list, setList] = useState<Client[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const [selected, setSelected] = useState<Client | null>(null);

  useEffect(() => {
    const h = setTimeout(() => setDebounced(search.trim()), 300);
    return () => clearTimeout(h);
  }, [search]);

  useEffect(() => {
    setLoading(true);
    setErr('');
    const qs = debounced ? `?search=${encodeURIComponent(debounced)}` : '';
    get(`/api/manage/clients/${qs}`)
      .then((d: any) => setList((d?.results ?? d) as Client[]))
      .catch((e) => {
        setErr((e as ApiError).message);
        setList(null);
      })
      .finally(() => setLoading(false));
  }, [debounced]);

  const columns: Column<Client>[] = [
    {
      key: 'client',
      header: t('common.client'),
      sortValue: (c) => c.full_name || c.phone,
      render: (c) => (
        <div>
          <div className="strong">{c.full_name || '—'}</div>
          <div className="muted mono" style={{ fontSize: 12.5 }}>{c.phone} · {c.client_code || '—'}</div>
        </div>
      ),
    },
    { key: 'pickup', header: t('wh.pvz'), render: (c) => <span style={{ fontSize: 13 }}>{c.pickup_point_title || '—'}</span> },
    { key: 'orders', header: t('clients.orders'), align: 'right', sortValue: (c) => c.orders_count, render: (c) => <span className="num">{c.orders_count}</span> },
    { key: 'parcels', header: t('clients.parcels'), align: 'right', sortValue: (c) => c.parcels_count, render: (c) => <span className="num">{c.parcels_count}</span> },
    { key: 'created', header: t('wh.created'), align: 'right', sortValue: (c) => c.created_at, render: (c) => <span className="num">{fmtDate(c.created_at)}</span> },
  ];

  return (
    <div>
      <PageHeader title={t('clients.title')} subtitle={t('clients.subtitle')} />

      <Card>
        <CardHeader
          title={t('clients.title')}
          actions={list && <span className="filter-count">{list.length}</span>}
        />
        <div className="card-body" style={{ paddingBottom: 0 }}>
          <Field label={t('clients.search')} style={{ maxWidth: 420 }}>
            <Input
              icon={<IconSearch size={18} />}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('clients.searchPlaceholder')}
              autoComplete="off"
            />
          </Field>
        </div>
        {err ? (
          <div className="card-body"><Alert variant="error">{err}</Alert></div>
        ) : (
          <DataTable
            columns={columns}
            rows={list}
            loading={loading}
            getRowKey={(c) => c.id}
            onRowClick={(c) => setSelected(c)}
            empty={<EmptyState icon={<IconStaff size={26} />} title={t('clients.empty')} description={t('clients.emptyDesc')} />}
          />
        )}
      </Card>

      {selected && <ClientDrawer client={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function ClientDrawer({ client, onClose }: { client: Client; onClose: () => void }) {
  const { t } = useI18n();
  const [data, setData] = useState<History | null>(null);
  const [err, setErr] = useState('');

  useEffect(() => {
    get<History>(`/api/manage/clients/${client.id}/history/`)
      .then(setData)
      .catch((e) => setErr((e as ApiError).message));
  }, [client.id]);

  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onEsc);
    return () => window.removeEventListener('keydown', onEsc);
  }, [onClose]);

  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label={t('clients.history')}>
        <div className="drawer-head">
          <div className="grow">
            <div className="track">{client.full_name || client.phone}</div>
            <div className="muted mono" style={{ fontSize: 12.5 }}>{client.phone} · {client.client_code || '—'}</div>
          </div>
          <button className="x" onClick={onClose} aria-label={t('common.cancel')}>
            <IconClose size={20} />
          </button>
        </div>
        <div className="drawer-body">
          {err && <Alert variant="error">{err}</Alert>}

          <div className="section-title" style={{ marginTop: 0 }}>{t('clients.orders')} · {data?.orders.length ?? '…'}</div>
          {!data ? (
            <p className="muted" style={{ fontSize: 13 }}>{t('common.loading')}</p>
          ) : data.orders.length === 0 ? (
            <p className="muted" style={{ fontSize: 13 }}>{t('clients.noOrders')}</p>
          ) : (
            <div className="stack gap-sm">
              {data.orders.map((o) => (
                <div key={o.id} className="hist-item">
                  <div className="grow" style={{ minWidth: 0 }}>
                    <div className="strong truncate">{o.product_title || '—'}</div>
                    <div className="muted mono" style={{ fontSize: 12 }}>{o.track_number || '—'}</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div className="num strong">{o.price ? `$${o.price}` : '—'}{o.quantity > 1 ? ` ×${o.quantity}` : ''}</div>
                    <div className="muted" style={{ fontSize: 12 }}>{o.status_display_name} · {fmtDate(o.created_at)}</div>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="section-title">{t('clients.parcels')} · {data?.parcels.length ?? '…'}</div>
          {!data ? null : data.parcels.length === 0 ? (
            <p className="muted" style={{ fontSize: 13 }}>{t('clients.noParcels')}</p>
          ) : (
            <div className="stack gap-sm">
              {data.parcels.map((p) => {
                const meta = statusMeta(p.status);
                return (
                  <div key={p.id} className="hist-item">
                    <span className="pi-ico"><IconBox size={16} /></span>
                    <div className="grow" style={{ minWidth: 0 }}>
                      <div className="mono strong">{p.track_number}</div>
                      <div className="muted" style={{ fontSize: 12 }}>{fmtDate(p.created_at)}</div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <Badge variant={meta.tone} dot>{t(`status.${p.status}`)}</Badge>
                      <div className="muted num" style={{ fontSize: 12, marginTop: 3 }}>
                        {p.weight ? `${p.weight} кг` : '—'}{p.delivery_price ? ` · $${p.delivery_price}` : ''}
                      </div>
                    </div>
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
