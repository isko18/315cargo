import { useEffect, useMemo, useState } from 'react';
import { money } from '../money';
import { ApiError, get, isPickupBound, post } from '../api';
import { statusMeta } from '../status';
import { usePickup } from '../pickupContext';
import { useI18n } from '../i18n';
import ParcelDrawer, { type Parcel } from '../components/ParcelDrawer';
import WeightInline from '../components/WeightInline';
import ClientSearch from '../components/ClientSearch';
import { IconSearch, IconBox, IconWeight, IconRevenue, IconWarehouse, IconDownload } from '../components/Icons';
import { downloadCsv, today } from '../csv';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  Checkbox,
  Column,
  DataTable,
  EmptyState,
  Field,
  formError,
  Input,
  PageHeader,
  Segmented,
  type SegmentedOption,
  Select,
  Stat,
  StatGrid,
} from '../ui';

const STATUS_ORDER = [
  'created',
  'purchased',
  'waiting_china_warehouse',
  'arrived_china_warehouse',
  'processing',
  'arrived_topa',
  'in_transit',
  'arrived_kyrgyzstan',
  'in_storage',
  'sent_to_kyrgyzstan',
  'at_pickup_point',
  'city_delivery',
  'delivered',
  'issued',
  'cancelled',
];

const fmtDate = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' }) : '—';

const num = (v?: string | null) => (v ? parseFloat(v) || 0 : 0);

export default function WarehousePage() {
  const { t } = useI18n();
  const { points, activeId } = usePickup();
  // Привязанный оператор ограничен своим ПВЗ на сервере — переключатель к нему
  // не применяем (иначе чужой activeId спрячет его же посылки).
  const bound = isPickupBound();
  const effectivePickup = bound ? null : activeId;
  const activePoint = points.find((p) => p.id === effectivePickup);
  const [list, setList] = useState<Parcel[] | null>(null);
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Parcel | null>(null);

  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const [status, setStatus] = useState('');
  const [pending, setPending] = useState(false);
  const [scope, setScope] = useState<'active' | 'archive' | 'all'>('active');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  useEffect(() => {
    const t = setTimeout(() => setDebounced(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    setLoading(true);
    setErr('');
    const params = new URLSearchParams();
    if (debounced) params.set('search', debounced);
    if (status) params.set('status', status);
    if (pending) params.set('pending', 'true');
    if (effectivePickup) params.set('pickup_point', String(effectivePickup));
    // Архив: при выбранном конкретном статусе показываем все с этим статусом
    // (в т.ч. выданные/архив), иначе — по сегменту Активные/Архив/Все.
    if (!status) {
      if (scope === 'active') params.set('archived', 'false');
      else if (scope === 'archive') params.set('archived', 'true');
    }
    if (dateFrom) params.set('date_from', dateFrom);
    if (dateTo) params.set('date_to', dateTo);
    const qs = params.toString();
    get(`/api/parcels/${qs ? `?${qs}` : ''}`)
      .then((d: any) => setList((d?.results ?? d) as Parcel[]))
      .catch((e) => {
        setErr((e as ApiError).message);
        setList(null);
      })
      .finally(() => setLoading(false));
  }, [debounced, status, pending, effectivePickup, scope, dateFrom, dateTo]);

  const summary = useMemo(() => {
    const rows = list ?? [];
    return {
      count: rows.length,
      weight: rows.reduce((s, p) => s + num(p.weight), 0),
      value: rows.reduce((s, p) => s + num(p.delivery_price), 0),
      noClient: rows.filter((p) => !p.client_code).length,
    };
  }, [list]);

  const hasFilters = Boolean(debounced || status || pending || scope !== 'active' || dateFrom || dateTo);

  function reset() {
    setSearch('');
    setStatus('');
    setPending(false);
    setScope('active');
    setDateFrom('');
    setDateTo('');
  }

  function exportCsv() {
    const rows = list ?? [];
    const header = ['Трек', 'Товар', 'Клиент', 'Код клиента', 'Телефон', 'Статус', 'Вес, кг', 'Стоимость, сом', 'ПВЗ', 'Создан'];
    const body = rows.map((p) => [
      p.track_number,
      p.product_title ?? '',
      p.client_name ?? '',
      p.client_code ?? '',
      p.client_phone ?? '',
      statusMeta(p.status).label,
      p.weight ?? '',
      p.delivery_price ?? '',
      p.pickup_point_title ?? '',
      p.created_at ? new Date(p.created_at).toLocaleString('ru-RU') : '',
    ]);
    downloadCsv(`sklad-${today()}.csv`, [header, ...body]);
  }

  // Инлайн-правки прямо на складе: вес (пересчёт цены) и присвоение клиента.
  async function saveWeight(id: number, weight: string) {
    setErr('');
    try {
      const u: any = await post(`/api/parcels/${id}/weight/`, { weight: weight ? weight : null });
      setList((l) =>
        l ? l.map((p) => (p.id === id ? { ...p, weight: u.weight, delivery_price: u.delivery_price } : p)) : l,
      );
    } catch (e) {
      setErr((e as ApiError).message);
      throw e;
    }
  }
  async function assignClient(id: number, code: string) {
    setErr('');
    try {
      const u: any = await post(`/api/parcels/${id}/assign/`, { client_code: code });
      setList((l) =>
        l
          ? l.map((p) =>
              p.id === id
                ? {
                    ...p,
                    client_code: u.client_code,
                    client_name: u.client_name,
                    pickup_point_title: u.pickup_point_title ?? p.pickup_point_title,
                  }
                : p,
            )
          : l,
      );
    } catch (e) {
      setErr(formError(e));
    }
  }

  const columns: Column<Parcel>[] = [
    {
      key: 'product',
      header: t('op.product'),
      sortValue: (p) => p.product_title ?? '',
      render: (p) => (
        <div className="cell-product">
          {p.product_image ? (
            <img src={p.product_image} alt="" className="thumb" />
          ) : (
            <span className="thumb thumb-fallback">
              <IconBox size={20} />
            </span>
          )}
          <span className="strong truncate" style={{ maxWidth: 200 }}>
            {p.product_title || '—'}
          </span>
        </div>
      ),
    },
    { key: 'track', header: t('common.track'), sortValue: (p) => p.track_number, render: (p) => <span className="mono">{p.track_number}</span> },
    {
      key: 'client',
      header: t('common.client'),
      sortValue: (p) => p.client_name ?? '￿',
      render: (p) =>
        p.client_code ? (
          <div>
            <div className="strong" style={{ fontSize: 13.5 }}>{p.client_name || '—'}</div>
            <div className="muted mono" style={{ fontSize: 12 }}>{p.client_code}</div>
          </div>
        ) : (
          <div onClick={(e) => e.stopPropagation()} style={{ minWidth: 190 }}>
            <ClientSearch
              size="sm"
              placeholder={t('scan.assignPlaceholder')}
              onPick={(c) => assignClient(p.id, c.client_code)}
            />
          </div>
        ),
    },
    {
      key: 'status',
      header: t('common.status'),
      render: (p) => (
        <Badge variant={statusMeta(p.status).tone} dot>
          {t(`status.${p.status}`)}
        </Badge>
      ),
    },
    {
      key: 'weight',
      header: t('op.weight'),
      align: 'right',
      sortValue: (p) => num(p.weight),
      render: (p) => <WeightInline value={p.weight} onSave={(w) => saveWeight(p.id, w)} />,
    },
    {
      key: 'price',
      header: t('wh.statValue'),
      align: 'right',
      sortValue: (p) => num(p.delivery_price),
      render: (p) => <span className="num">{money(p.delivery_price)}</span>,
    },
    { key: 'pickup', header: t('wh.pvz'), render: (p) => <span style={{ fontSize: 13 }}>{p.pickup_point_title || '—'}</span> },
    {
      key: 'created',
      header: t('wh.created'),
      align: 'right',
      sortValue: (p) => p.created_at ?? '',
      render: (p) => <span className="num">{fmtDate(p.created_at)}</span>,
    },
  ];

  return (
    <div>
      <PageHeader
        title={t('wh.title')}
        subtitle={
          <>
            {t('wh.subtitle')}
            {activePoint && (
              <> · {t('wh.pvz')}: <b>{activePoint.title}</b> ({t('wh.pvzHint')})</>
            )}
          </>
        }
      />

      <StatGrid className="mb-lg">
        <Stat icon={<IconBox size={19} />} tone="blue" label={`${t('wh.statParcels')}${hasFilters ? ` (${t('wh.statFilter')})` : ''}`} value={summary.count} />
        <Stat icon={<IconWarehouse size={19} />} tone="amber" label={t('wh.statNoClient')} value={summary.noClient} hint={t('wh.statNoClientHint')} />
        <Stat icon={<IconWeight size={19} />} tone="violet" label={t('wh.statWeight')} value={summary.weight.toFixed(2)} hint="кг" />
        <Stat icon={<IconRevenue size={19} />} tone="green" label={t('wh.statValue')} value={money(summary.value)} />
      </StatGrid>

      <Card>
        <CardBody>
          <div className="row">
            <Field label={t('wh.search')} style={{ flex: 3 }}>
              <Input
                icon={<IconSearch size={18} />}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t('wh.searchPlaceholder')}
                autoComplete="off"
              />
            </Field>
            <Field label={t('common.status')} style={{ flex: 2 }}>
              <Select value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="">{t('wh.statusAll')}</option>
                {STATUS_ORDER.map((s) => (
                  <option key={s} value={s}>
                    {t(`status.${s}`)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label={t('wh.createdFrom')} style={{ minWidth: 140 }}>
              <Input type="date" value={dateFrom} max={dateTo || undefined} onChange={(e) => setDateFrom(e.target.value)} />
            </Field>
            <Field label={t('wh.createdTo')} style={{ minWidth: 140 }}>
              <Input type="date" value={dateTo} min={dateFrom || undefined} onChange={(e) => setDateTo(e.target.value)} />
            </Field>
          </div>
          <div className="cluster mt-md">
            <Segmented
              options={[
                { value: 'active', label: t('wh.scopeActive') },
                { value: 'archive', label: t('wh.scopeArchive') },
                { value: 'all', label: t('wh.scopeAll') },
              ] as SegmentedOption<'active' | 'archive' | 'all'>[]}
              value={scope}
              onChange={setScope}
              ariaLabel={t('wh.scopeActive')}
            />
            <Checkbox checked={pending} onChange={setPending}>
              {t('wh.onlyPending')}
            </Checkbox>
            <span className="grow" />
            {hasFilters && (
              <Button variant="subtle" size="sm" onClick={reset}>
                {t('wh.resetFilters')}
              </Button>
            )}
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title={t('wh.parcels')}
          actions={
            <div className="cluster gap-sm">
              {list && <span className="filter-count">{list.length} {t('wh.pcs')}</span>}
              <Button
                variant="secondary"
                size="sm"
                onClick={exportCsv}
                disabled={!list || list.length === 0}
                icon={<IconDownload size={16} />}
              >
                CSV
              </Button>
            </div>
          }
        />
        {err ? (
          <CardBody>
            <Alert variant="error">{err}</Alert>
          </CardBody>
        ) : (
          <DataTable
            columns={columns}
            rows={list}
            loading={loading}
            getRowKey={(p) => p.id}
            onRowClick={(p) => setSelected(p)}
            initialSort={{ key: 'created', dir: 'desc' }}
            empty={
              <EmptyState
                icon={<IconWarehouse size={26} />}
                title={t('wh.emptyTitle')}
                description={hasFilters ? t('wh.emptyFiltered') : t('wh.emptyNone')}
                action={hasFilters ? <Button variant="subtle" size="sm" onClick={reset}>{t('wh.resetFilters')}</Button> : undefined}
              />
            }
          />
        )}
      </Card>

      {selected && <ParcelDrawer parcel={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
