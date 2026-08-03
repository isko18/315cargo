import { useEffect, useState } from 'react';
import { ApiError, get, patch } from '../api';
import { useI18n } from '../i18n';
import type { Tone } from '../status';
import { IconTruck } from '../components/Icons';
import { Alert, Badge, Card, CardHeader, Column, DataTable, EmptyState, PageHeader, Select } from '../ui';

type Request = {
  id: number;
  client_name: string | null;
  client_phone: string | null;
  client_code: string | null;
  track_number: string | null;
  address: string;
  recipient_name: string;
  recipient_phone: string;
  price: string | null;
  status: string;
  status_display_name: string;
  created_at: string;
};

const D_STATUSES = [
  'created',
  'price_calculated',
  'accepted',
  'assigned_to_courier',
  'in_delivery',
  'delivered',
  'cancelled',
];

const D_TONE: Record<string, Tone> = {
  created: 'gray',
  price_calculated: 'indigo',
  accepted: 'blue',
  assigned_to_courier: 'cyan',
  in_delivery: 'teal',
  delivered: 'green',
  cancelled: 'red',
};

const fmtDate = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' }) : '—';

export default function DeliveryPage() {
  const { t } = useI18n();
  const [list, setList] = useState<Request[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');

  function reload() {
    setLoading(true);
    get('/api/manage/city-delivery/')
      .then((d: any) => setList((d?.results ?? d) as Request[]))
      .catch((e) => {
        setErr((e as ApiError).message);
        setList(null);
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    reload();
  }, []);

  async function changeStatus(id: number, status: string) {
    setErr('');
    setMsg('');
    try {
      const updated = await patch<Request>(`/api/manage/city-delivery/${id}/`, { status });
      setList((l) => (l ? l.map((r) => (r.id === id ? { ...r, ...updated } : r)) : l));
      setMsg(t('delivery.statusSaved'));
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  const columns: Column<Request>[] = [
    {
      key: 'client',
      header: t('common.client'),
      sortValue: (r) => r.client_name ?? '',
      render: (r) => (
        <div>
          <div className="strong">{r.client_name || '—'}</div>
          <div className="muted mono" style={{ fontSize: 12 }}>{r.client_phone} · {r.client_code || '—'}</div>
        </div>
      ),
    },
    { key: 'track', header: t('common.track'), render: (r) => <span className="mono">{r.track_number || '—'}</span> },
    {
      key: 'recipient',
      header: t('delivery.recipient'),
      render: (r) => (
        <div style={{ maxWidth: 240 }}>
          <div className="truncate">{r.recipient_name}</div>
          <div className="muted mono" style={{ fontSize: 12 }}>{r.recipient_phone}</div>
          <div className="muted truncate" style={{ fontSize: 12 }}>{r.address}</div>
        </div>
      ),
    },
    { key: 'price', header: t('op.priceUsd'), align: 'right', sortValue: (r) => parseFloat(r.price || '0'), render: (r) => <span className="num">{r.price ? `$${r.price}` : '—'}</span> },
    { key: 'created', header: t('wh.created'), align: 'right', sortValue: (r) => r.created_at, render: (r) => <span className="num">{fmtDate(r.created_at)}</span> },
    {
      key: 'status',
      header: t('common.status'),
      render: (r) => (
        <div className="cluster gap-sm" style={{ flexWrap: 'nowrap' }}>
          <Badge variant={D_TONE[r.status] ?? 'gray'} dot>{r.status_display_name}</Badge>
          <Select
            value={r.status}
            onChange={(e) => changeStatus(r.id, e.target.value)}
            style={{ padding: '5px 8px', fontSize: 12.5, width: 'auto', maxWidth: 180 }}
          >
            {D_STATUSES.map((s) => (
              <option key={s} value={s}>{t(`dstatus.${s}`)}</option>
            ))}
          </Select>
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader title={t('delivery.title')} subtitle={t('delivery.subtitle')} />

      {msg && <Alert variant="success">{msg}</Alert>}

      <Card>
        <CardHeader title={t('delivery.title')} actions={list && <span className="filter-count">{list.length}</span>} />
        {err ? (
          <div className="card-body"><Alert variant="error">{err}</Alert></div>
        ) : (
          <DataTable
            columns={columns}
            rows={list}
            loading={loading}
            getRowKey={(r) => r.id}
            initialSort={{ key: 'created', dir: 'desc' }}
            empty={<EmptyState icon={<IconTruck size={26} />} title={t('delivery.empty')} description={t('delivery.emptyDesc')} />}
          />
        )}
      </Card>
    </div>
  );
}
