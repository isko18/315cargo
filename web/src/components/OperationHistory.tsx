import { useEffect, useMemo, useState } from 'react';
import { money } from '../money';
import { ApiError, get, getRole, post } from '../api';
import { useI18n } from '../i18n';
import { IconHistory, IconSearch } from './Icons';
import WeightInline from './WeightInline';
import ClientSearch from './ClientSearch';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  Column,
  DataTable,
  EmptyState,
  Field,
  formError,
  Input,
  Select,
} from '../ui';

type Op = {
  id: number;
  parcel: number;
  type: 'receive' | 'issue' | 'china';
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
type Operator = { id: number; full_name: string; phone: string };

const num = (v?: string | null) => (v ? parseFloat(v) || 0 : 0);
const fmt = (iso: string) =>
  new Date(iso).toLocaleString('ru-RU', {
    day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit',
  });

/**
 * История операций приём/выдача с фильтрами и инлайн-редактированием веса.
 * Оператор видит только свои операции, владелец/админ — все по карго.
 */
export default function OperationHistory({
  type,
  reloadSignal = 0,
}: {
  type: 'receive' | 'issue' | 'china';
  reloadSignal?: number;
}) {
  const { t } = useI18n();
  const role = getRole();
  const isManager = Boolean(role.is_superuser || role.is_cargo_admin);

  const [rows, setRows] = useState<Op[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [operator, setOperator] = useState('');
  const [operators, setOperators] = useState<Operator[]>([]);

  useEffect(() => {
    if (!isManager) return;
    get('/api/manage/staff/')
      .then((d: any) => setOperators((d?.results ?? d) as Operator[]))
      .catch(() => {});
  }, [isManager]);

  useEffect(() => {
    const h = setTimeout(() => setDebounced(search.trim()), 300);
    return () => clearTimeout(h);
  }, [search]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr('');
    const p = new URLSearchParams({ type });
    if (debounced) p.set('search', debounced);
    if (dateFrom) p.set('date_from', dateFrom);
    if (dateTo) p.set('date_to', dateTo);
    if (operator) p.set('operator', operator);
    get(`/api/history/?${p.toString()}`)
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
  }, [type, reloadSignal, debounced, dateFrom, dateTo, operator]);

  // Присвоение клиента «ничьей» посылке прямо из истории.
  async function assign(parcelId: number, code: string) {
    setErr('');
    try {
      const updated: any = await post(`/api/parcels/${parcelId}/assign/`, { client_code: code });
      setRows((rs) =>
        rs
          ? rs.map((r) =>
              r.parcel === parcelId
                ? {
                    ...r,
                    client_code: updated.client_code,
                    client_name: updated.client_name,
                    pickup_point_title: updated.pickup_point_title ?? r.pickup_point_title,
                  }
                : r,
            )
          : rs,
      );
    } catch (e) {
      setErr(formError(e));
    }
  }

  // Инлайн-изменение веса прямо в истории (пересчёт цены на бэкенде).
  async function saveWeight(parcelId: number, weight: string) {
    setErr('');
    try {
      const updated: any = await post(`/api/parcels/${parcelId}/weight/`, {
        weight: weight ? weight : null,
      });
      setRows((rs) =>
        rs
          ? rs.map((r) =>
              r.parcel === parcelId
                ? { ...r, weight: updated.weight, delivery_price: updated.delivery_price }
                : r,
            )
          : rs,
      );
    } catch (e) {
      setErr(formError(e));
      throw e; // чтобы WeightInline вернул прежнее значение
    }
  }

  const totals = useMemo(() => {
    const l = rows ?? [];
    return {
      count: l.length,
      weight: l.reduce((s, r) => s + num(r.weight), 0),
      price: l.reduce((s, r) => s + num(r.delivery_price), 0),
    };
  }, [rows]);

  const hasFilters = Boolean(debounced || dateFrom || dateTo || operator);
  function reset() {
    setSearch('');
    setDateFrom('');
    setDateTo('');
    setOperator('');
  }

  const columns: Column<Op>[] = [
    {
      key: 'product',
      header: t('op.product'),
      render: (r) => (
        <span className="truncate" style={{ maxWidth: 170, display: 'inline-block' }}>
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
          <div style={{ minWidth: 190 }}>
            <ClientSearch
              size="sm"
              placeholder={t('scan.assignPlaceholder')}
              onPick={(c) => assign(r.parcel, c.client_code)}
            />
          </div>
        ),
    },
    {
      key: 'weight',
      header: t('op.weightKg'),
      align: 'right',
      render: (r) => <WeightInline value={r.weight} onSave={(w) => saveWeight(r.parcel, w)} />,
    },
    {
      key: 'price',
      header: t('op.price'),
      align: 'right',
      render: (r) => <span className="num">{money(r.delivery_price)}</span>,
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

  const title =
    type === 'issue'
      ? t('hist.issueHistory')
      : type === 'china'
        ? t('hist.chinaHistory')
        : t('hist.receiveHistory');

  return (
    <Card>
      <CardHeader
        title={title}
        description={isManager ? t('hist.scopeCargo') : t('hist.scopeMine')}
        actions={
          rows && (
            <div className="cluster gap-sm">
              <Badge variant="plain">{totals.count} {t('wh.pcs')}</Badge>
              <Badge variant="violet">{totals.weight.toFixed(2)} кг</Badge>
              <Badge variant="green">{money(totals.price)}</Badge>
            </div>
          )
        }
      />
      <CardBody>
        <div className="row">
          <Field label={t('common.search')} style={{ flex: 3 }}>
            <Input
              icon={<IconSearch size={18} />}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('hist.searchPlaceholder')}
              autoComplete="off"
            />
          </Field>
          {isManager && (
            <Field label={t('hist.operator')} style={{ flex: 2 }}>
              <Select value={operator} onChange={(e) => setOperator(e.target.value)}>
                <option value="">{t('hist.allOperators')}</option>
                {operators.map((o) => (
                  <option key={o.id} value={o.id}>{o.full_name || o.phone}</option>
                ))}
              </Select>
            </Field>
          )}
          <Field label={t('wh.createdFrom')} style={{ minWidth: 140 }}>
            <Input type="date" value={dateFrom} max={dateTo || undefined} onChange={(e) => setDateFrom(e.target.value)} />
          </Field>
          <Field label={t('wh.createdTo')} style={{ minWidth: 140 }}>
            <Input type="date" value={dateTo} min={dateFrom || undefined} onChange={(e) => setDateTo(e.target.value)} />
          </Field>
          {hasFilters && (
            <Button variant="subtle" size="sm" onClick={reset} style={{ alignSelf: 'flex-end' }}>
              {t('wh.resetFilters')}
            </Button>
          )}
        </div>
        {err && <Alert variant="error">{err}</Alert>}
      </CardBody>
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
            description={
              hasFilters
                ? t('hist.emptyFiltered')
                : type === 'issue'
                  ? t('hist.emptyNoneIssue')
                  : type === 'china'
                    ? t('hist.emptyNoneChina')
                    : t('hist.emptyNoneReceive')
            }
          />
        }
      />
    </Card>
  );
}
