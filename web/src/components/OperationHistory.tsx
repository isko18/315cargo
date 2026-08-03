import { useEffect, useState } from 'react';
import { ApiError, get, getRole } from '../api';
import { useI18n } from '../i18n';
import { IconHistory } from './Icons';
import { Alert, Badge, Card, CardHeader, Column, DataTable, EmptyState } from '../ui';

type Op = {
  id: number;
  type: 'receive' | 'issue';
  track_number: string;
  client_code: string | null;
  client_name: string | null;
  product_title: string | null;
  weight: string | null;
  delivery_price: string | null;
  operator_name: string | null;
  operator_phone: string | null;
  pickup_point_title: string | null;
  created_at: string;
};

const fmt = (iso: string) =>
  new Date(iso).toLocaleString('ru-RU', {
    day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit',
  });

/**
 * Инлайн-история операций для страниц «Приём»/«Выдача».
 * Оператор видит только свои операции, владелец/админ — все по карго.
 * ``reloadSignal`` — меняйте после операции, чтобы обновить список.
 */
export default function OperationHistory({
  type,
  reloadSignal = 0,
}: {
  type: 'receive' | 'issue';
  reloadSignal?: number;
}) {
  const { t } = useI18n();
  const role = getRole();
  const isManager = Boolean(role.is_superuser || role.is_cargo_admin);
  const [rows, setRows] = useState<Op[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr('');
    get(`/api/history/?type=${type}`)
      .then((d: any) => {
        if (!cancelled) setRows((d?.results ?? d) as Op[]);
      })
      .catch((e) => {
        if (!cancelled) {
          setErr((e as ApiError).message);
          setRows(null);
        }
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [type, reloadSignal]);

  const columns: Column<Op>[] = [
    {
      key: 'product',
      header: t('op.product'),
      render: (r) => (
        <span className="truncate" style={{ maxWidth: 180, display: 'inline-block' }}>
          {r.product_title || '—'}
        </span>
      ),
    },
    { key: 'track', header: t('common.track'), render: (r) => <span className="mono">{r.track_number}</span> },
    {
      key: 'client',
      header: t('common.client'),
      render: (r) =>
        r.client_code ? (
          <div>
            <div className="strong" style={{ fontSize: 13 }}>{r.client_name || '—'}</div>
            <div className="muted mono" style={{ fontSize: 12 }}>{r.client_code}</div>
          </div>
        ) : (
          <Badge variant="warn">{t('common.noClient')}</Badge>
        ),
    },
    { key: 'weight', header: t('op.weightKg'), align: 'right', render: (r) => <span className="num">{r.weight ?? '—'}</span> },
    {
      key: 'price',
      header: t('op.priceUsd'),
      align: 'right',
      render: (r) => <span className="num">{r.delivery_price ? `$${r.delivery_price}` : '—'}</span>,
    },
    ...(isManager
      ? ([
          {
            key: 'operator',
            header: t('hist.operator'),
            render: (r: Op) => <span style={{ fontSize: 13 }}>{r.operator_name || r.operator_phone || '—'}</span>,
          },
        ] as Column<Op>[])
      : []),
    {
      key: 'date',
      header: t('hist.date'),
      align: 'right',
      sortValue: (r) => r.created_at,
      render: (r) => <span className="num" style={{ fontSize: 12.5 }}>{fmt(r.created_at)}</span>,
    },
  ];

  const title = type === 'issue' ? t('hist.issueHistory') : t('hist.receiveHistory');

  return (
    <Card>
      <CardHeader
        title={title}
        description={isManager ? t('hist.scopeCargo') : t('hist.scopeMine')}
        actions={rows && <Badge variant="plain">{rows.length} {t('wh.pcs')}</Badge>}
      />
      {err ? (
        <div style={{ padding: '0 20px 16px' }}><Alert variant="error">{err}</Alert></div>
      ) : (
        <DataTable
          columns={columns}
          rows={rows}
          loading={loading}
          getRowKey={(r) => r.id}
          initialSort={{ key: 'date', dir: 'desc' }}
          empty={
            <EmptyState
              icon={<IconHistory size={26} />}
              title={t('hist.emptyTitle')}
              description={type === 'issue' ? t('hist.emptyNoneIssue') : t('hist.emptyNoneReceive')}
            />
          }
        />
      )}
    </Card>
  );
}
