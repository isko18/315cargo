import { useEffect, useMemo, useState } from 'react';
import { ApiError, get } from '../api';
import { statusMeta } from '../status';
import { usePickup } from '../pickupContext';
import { useI18n } from '../i18n';
import { IconRevenue, IconWeight, IconIssue, IconBox, IconStaff, IconTariff, IconAnalytics, IconDownload } from '../components/Icons';
import { downloadCsv, today } from '../csv';
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
  Input,
  PageHeader,
  Segmented,
  Skeleton,
  Stat,
  StatGrid,
  type SegmentedOption,
} from '../ui';

type Point = { date: string; count: number; revenue: number };
type TopClient = { client_code: string; full_name: string; count: number; revenue: number };
type Pickup = { title: string; count: number; revenue: number };

type Dashboard = {
  cargo: { id: number; title: string; slug: string };
  price_per_kg_usd: number;
  pickup: { id: number | null; title: string | null };
  period: { key: string; from: string | null; to: string };
  period_issued_count: number;
  period_revenue_usd: number;
  period_weight_kg: number;
  period_avg_check_usd: number;
  period_avg_weight_kg: number;
  period_received_count: number;
  timeseries: Point[];
  top_clients: TopClient[];
  by_pickup: Pickup[];
  parcels_by_status: Record<string, number>;
  users_count: number;
  pickup_points_count: number;
  orders_count: number;
  parcels_count: number;
  parcels_pending_count: number;
  issued_count: number;
  issued_revenue_usd: number;
  issued_weight_kg: number;
  total_weight_kg: number;
  potential_revenue_usd: number;
};

const PERIOD_KEYS = ['today', '7d', '30d', '90d', '365d', 'all'] as const;

const money = (v: number) => `$${v.toFixed(2)}`;
const kg = (v: number) => `${v.toFixed(2)} кг`;
const fmtDay = (iso: string) => {
  const [, m, d] = iso.split('-');
  return `${d}.${m}`;
};

export default function AnalyticsPage() {
  const { t } = useI18n();
  const { activeId } = usePickup();
  const PERIODS: SegmentedOption<string>[] = PERIOD_KEYS.map((k) => ({ value: k, label: t(`an.period.${k}`) }));
  const [d, setD] = useState<Dashboard | null>(null);
  const [err, setErr] = useState('');
  const [noCargo, setNoCargo] = useState(false);
  const [loading, setLoading] = useState(true);

  const [period, setPeriod] = useState('30d');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const custom = Boolean(from || to);

  useEffect(() => {
    setLoading(true);
    setErr('');
    const params = new URLSearchParams();
    if (custom) {
      params.set('from', from || '');
      params.set('to', to || '');
    } else {
      params.set('period', period);
    }
    if (activeId) params.set('pickup_point', String(activeId));
    get<Dashboard>(`/api/manage/dashboard/?${params.toString()}`)
      .then((data) => {
        setD(data);
        setNoCargo(false);
      })
      .catch((e) => {
        const ae = e as ApiError;
        if (ae.status === 404 || /карго/i.test(ae.message)) setNoCargo(true);
        else setErr(ae.message);
      })
      .finally(() => setLoading(false));
  }, [period, from, to, custom, activeId]);

  if (noCargo)
    return (
      <div>
        <PageHeader title={t('an.title')} subtitle={t('an.noCargoSub')} />
        <Card pad>
          <EmptyState
            icon={<IconAnalytics size={26} />}
            title={t('an.noCargoTitle')}
            description={
              <>
                {t('an.noCargoSub')} — <b>{t('nav.overview')}</b>.
              </>
            }
          />
        </Card>
      </div>
    );

  if (err)
    return (
      <div>
        <PageHeader title={t('an.title')} />
        <Alert variant="error">{err}</Alert>
      </div>
    );

  const topClientColumns: Column<TopClient & { rank: number }>[] = [
    { key: 'rank', header: '', width: 34, render: (c) => <span className="rank">{c.rank}</span> },
    {
      key: 'client',
      header: t('an.colClient'),
      render: (c) => (
        <div>
          <div className="strong">{c.full_name || '—'}</div>
          <div className="muted mono" style={{ fontSize: 12.5 }}>{c.client_code}</div>
        </div>
      ),
    },
    { key: 'count', header: t('an.colIssues'), align: 'right', render: (c) => <span className="num">{c.count}</span> },
    { key: 'revenue', header: t('an.colRevenue'), align: 'right', render: (c) => <span className="num">{money(c.revenue)}</span> },
  ];

  return (
    <div>
      <PageHeader
        title={`${t('an.title')}${d ? ` — ${d.cargo.title}` : ''}`}
        subtitle={
          <>
            {t('an.subtitle')}
            {d?.pickup?.title && (
              <> · {t('wh.pvz')}: <b>{d.pickup.title}</b> ({t('wh.pvzHint')})</>
            )}
          </>
        }
      />

      <div className="toolbar">
        <Segmented
          options={PERIODS}
          value={custom ? null : period}
          ariaLabel={t('nav.analytics')}
          onChange={(v) => {
            setFrom('');
            setTo('');
            setPeriod(v);
          }}
        />
        <div className="daterange">
          <Input type="date" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} aria-label={t('wh.createdFrom')} />
          <span>—</span>
          <Input type="date" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} aria-label={t('wh.createdTo')} />
          {custom && (
            <Button variant="subtle" size="sm" onClick={() => { setFrom(''); setTo(''); }}>
              {t('an.reset')}
            </Button>
          )}
        </div>
        <span className="grow" />
        {d && (
          <span className="period-note">
            {d.period.from ? `${fmtDay(d.period.from)} — ${fmtDay(d.period.to)}` : `${t('an.allTo')} ${fmtDay(d.period.to)}`}
          </span>
        )}
      </div>

      {loading || !d ? (
        <SkeletonGrid />
      ) : (
        <>
          <StatGrid className="mb-lg">
            <Stat icon={<IconRevenue size={19} />} tone="green" label={t('an.kpiRevenue')} value={money(d.period_revenue_usd)} hint={`${d.period_issued_count} ${t('an.issues')}`} />
            <Stat icon={<IconIssue size={19} />} tone="blue" label={t('an.kpiIssued')} value={String(d.period_issued_count)} hint={`${t('an.received')}: ${d.period_received_count}`} />
            <Stat icon={<IconTariff size={19} />} tone="violet" label={t('an.kpiCheck')} value={money(d.period_avg_check_usd)} hint={t('an.perParcel')} />
            <Stat icon={<IconWeight size={19} />} tone="amber" label={t('an.kpiAvgWeight')} value={kg(d.period_avg_weight_kg)} hint={`${t('an.totalShort')} ${kg(d.period_weight_kg)}`} />
          </StatGrid>

          <Card>
            <CardHeader
              title={t('an.revByDay')}
              description={t('an.revByDayDesc')}
              actions={
                <Button
                  variant="secondary"
                  size="sm"
                  icon={<IconDownload size={16} />}
                  disabled={d.timeseries.length === 0}
                  onClick={() =>
                    downloadCsv(`analytics-${today()}.csv`, [
                      [t('wh.created'), t('an.colIssues'), t('op.priceUsd')],
                      ...d.timeseries.map((p) => [p.date, p.count, p.revenue]),
                    ])
                  }
                >
                  CSV
                </Button>
              }
            />
            <CardBody>
              <RevenueChart data={d.timeseries} />
            </CardBody>
          </Card>

          <div className="two-col">
            <Card>
              <CardHeader title={t('an.topClients')} description={t('an.topClientsDesc')} />
              <DataTable
                columns={topClientColumns}
                rows={d.top_clients.map((c, i) => ({ ...c, rank: i + 1 }))}
                getRowKey={(c) => c.client_code + c.rank}
                empty={<EmptyState compact title={t('an.noPeriodData')} />}
              />
            </Card>

            <Card>
              <CardHeader title={t('an.byPickup')} description={t('an.topClientsDesc')} />
              {d.by_pickup.length === 0 ? (
                <EmptyState compact title={t('an.noPeriodData')} />
              ) : (
                <CardBody>
                  <PickupBars data={d.by_pickup} />
                </CardBody>
              )}
            </Card>
          </div>

          <Card>
            <CardHeader
              title={t('an.byStatus')}
              description={t('an.byStatusDesc')}
              actions={
                <div className="cluster gap-sm">
                  <Badge variant="plain">{d.parcels_count} {t('an.totalShort')}</Badge>
                  <Badge variant="warn">{d.parcels_pending_count} {t('an.noClientBadge')}</Badge>
                </div>
              }
            />
            <CardBody>
              <StatusBars data={d.parcels_by_status} />
            </CardBody>
          </Card>

          <Card>
            <CardHeader title={t('an.allTime')} />
            <CardBody>
              <StatGrid>
                <Stat icon={<IconRevenue size={19} />} tone="green" label={t('an.atRevenue')} value={money(d.issued_revenue_usd)} hint={`${d.issued_count} ${t('an.parcelsWord')}`} />
                <Stat icon={<IconTariff size={19} />} tone="amber" label={t('an.atPotential')} value={money(d.potential_revenue_usd)} hint={t('an.atIfAll')} />
                <Stat icon={<IconBox size={19} />} tone="gray" label={t('an.atParcelsOrders')} value={`${d.parcels_count} / ${d.orders_count}`} />
                <Stat icon={<IconStaff size={19} />} tone="teal" label={t('an.clientsWord')} value={String(d.users_count)} hint={`${t('wh.pvz')}: ${d.pickup_points_count}`} />
              </StatGrid>
            </CardBody>
          </Card>
        </>
      )}
    </div>
  );
}

function SkeletonGrid() {
  return (
    <StatGrid className="mb-lg">
      {Array.from({ length: 4 }).map((_, i) => (
        <div className="stat" key={i}>
          <Skeleton height={16} width="60%" />
          <Skeleton height={28} width="45%" style={{ marginTop: 10 }} />
          <Skeleton height={12} width="35%" style={{ marginTop: 8 }} />
        </div>
      ))}
    </StatGrid>
  );
}

function RevenueChart({ data }: { data: Point[] }) {
  const { t } = useI18n();
  const [hover, setHover] = useState<number | null>(null);
  const max = useMemo(() => Math.max(1, ...data.map((p) => p.revenue)), [data]);
  const totalRev = useMemo(() => data.reduce((s, p) => s + p.revenue, 0), [data]);

  if (data.length === 0) return <p className="muted">{t('an.noData')}</p>;

  const step = Math.max(1, Math.ceil(data.length / 6));
  const labels = data.filter((_, i) => i % step === 0 || i === data.length - 1);

  return (
    <div className="chart">
      <div className="chart-head">
        <span className="strong">{money(totalRev)}</span>
        <span className="muted" style={{ fontSize: 13 }}>{t('an.forPeriod')}</span>
        <span className="cmax">{t('an.maxDay')}: {money(max)}</span>
      </div>
      <div className="chart-plot" onMouseLeave={() => setHover(null)}>
        <div className="chart-grid">
          {[0.25, 0.5, 0.75].map((f) => (
            <span key={f} style={{ top: `${(1 - f) * 100}%` }} />
          ))}
        </div>
        {data.map((p, i) => (
          <div key={p.date} className={`chart-col ${p.revenue === 0 ? 'empty' : ''}`} onMouseEnter={() => setHover(i)}>
            <div className="cbar" style={{ height: `${p.revenue === 0 ? 2 : Math.max(4, (p.revenue / max) * 100)}%` }} />
          </div>
        ))}
        {hover !== null && (
          <div className="chart-tip" style={{ left: `${((hover + 0.5) / data.length) * 100}%`, top: 4 }}>
            <div className="tip-date">{fmtDay(data[hover].date)}</div>
            <b>{money(data[hover].revenue)}</b> · {data[hover].count} {t('an.issues')}
          </div>
        )}
      </div>
      <div className="chart-axis">
        {labels.map((p) => (
          <span key={p.date}>{fmtDay(p.date)}</span>
        ))}
      </div>
    </div>
  );
}

function PickupBars({ data }: { data: Pickup[] }) {
  const max = Math.max(1, ...data.map((p) => p.count));
  return (
    <div className="bars">
      {data.map((p) => (
        <div className="bar-row tone-violet" key={p.title}>
          <div className="bar-label">
            <span className="dot" />
            {p.title}
          </div>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(p.count / max) * 100}%` }} />
          </div>
          <div className="bar-value">{p.count}</div>
        </div>
      ))}
    </div>
  );
}

function StatusBars({ data }: { data: Record<string, number> }) {
  const { t } = useI18n();
  const rows = Object.entries(data).sort((a, b) => b[1] - a[1]);
  if (rows.length === 0) return <p className="muted">{t('an.noParcels')}</p>;
  const max = Math.max(1, ...rows.map(([, n]) => n));
  return (
    <div className="bars">
      {rows.map(([status, n]) => {
        const meta = statusMeta(status);
        return (
          <div className={`bar-row tone-${meta.tone}`} key={status}>
            <div className="bar-label">
              <span className="dot" />
              {t(`status.${status}`)}
            </div>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${(n / max) * 100}%` }} />
            </div>
            <div className="bar-value">{n}</div>
          </div>
        );
      })}
    </div>
  );
}
