import { useEffect, useMemo, useState } from 'react';
import { money } from '../money';
import { useNavigate, useParams } from 'react-router-dom';
import { ApiError, get } from '../api';
import { useI18n } from '../i18n';
import { statusMeta, type Tone } from '../status';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  Column,
  DataTable,
  EmptyState,
  Modal,
  PageHeader,
  Segmented,
  type SegmentedOption,
  Skeleton,
  Stat,
  StatGrid,
} from '../ui';
import {
  IconWarehouse,
  IconStaff,
  IconBox,
  IconRevenue,
  IconIssue,
  IconOverview,
} from '../components/Icons';

type CargoInfo = {
  id: number;
  title: string;
  slug: string;
  phone: string;
  address: string;
  price_per_kg_kgs: number;
  is_active: boolean;
};
type Totals = {
  clients: number;
  staff: number;
  pickups: number;
  parcels: number;
  at_warehouse: number;
  issued: number;
  unassigned_pickup: number;
  revenue_issued: number;
  weight_issued: number;
};
type PickupRow = {
  id: number;
  title: string;
  address: string;
  is_active: boolean;
  clients: number;
  staff: number;
  parcels: number;
  at_warehouse: number;
  issued: number;
};
type StaffRow = {
  id: number;
  full_name: string;
  phone: string;
  is_cargo_admin: boolean;
  is_china_staff: boolean;
  is_active: boolean;
  pickup_point_title: string | null;
};
type Detail = {
  cargo: CargoInfo;
  totals: Totals;
  parcels_by_status: Record<string, number>;
  pickups: PickupRow[];
  staff: StaffRow[];
};

type ParcelRow = {
  id: number;
  track_number: string;
  status: string;
  client_code: string | null;
  client_name: string | null;
  product_title?: string | null;
  weight: string | null;
  delivery_price: string | null;
};
type PFilter = 'stock' | 'all';
const AT_PICKUP = 'at_pickup_point';
const pnum = (v?: string | null) => (v ? parseFloat(v) || 0 : 0);

export default function CargoDetailPage() {
  const { t } = useI18n();
  const { id } = useParams();
  const nav = useNavigate();
  const [data, setData] = useState<Detail | null>(null);
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(true);

  // Дрилл-даун по складу: клик на ПВЗ → его посылки.
  const [pickupSel, setPickupSel] = useState<PickupRow | null>(null);
  const [pFilter, setPFilter] = useState<PFilter>('stock');
  const [pList, setPList] = useState<ParcelRow[] | null>(null);
  const [pLoading, setPLoading] = useState(false);
  const [pErr, setPErr] = useState('');

  useEffect(() => {
    setLoading(true);
    get<Detail>(`/api/admin/cargos/${id}/detail/`)
      .then((d) => setData(d))
      .catch((e) => setErr((e as ApiError).message))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    if (!pickupSel) return;
    let cancelled = false;
    setPLoading(true);
    setPErr('');
    const params = new URLSearchParams({ pickup_point: String(pickupSel.id) });
    if (pFilter === 'stock') {
      params.set('status', AT_PICKUP);
      params.set('archived', 'false');
    }
    get(`/api/parcels/?${params.toString()}`)
      .then((d: any) => {
        if (!cancelled) setPList((d?.results ?? d) as ParcelRow[]);
      })
      .catch((e) => {
        if (!cancelled) {
          setPErr((e as ApiError).message);
          setPList(null);
        }
      })
      .finally(() => !cancelled && setPLoading(false));
    return () => {
      cancelled = true;
    };
  }, [pickupSel, pFilter]);

  function openPickup(p: PickupRow) {
    setPickupSel(p);
    setPFilter('stock');
    setPList(null);
  }

  function roleLabel(s: StaffRow) {
    if (s.is_cargo_admin) return t('roles.cargoAdmin');
    if (s.is_china_staff) return t('roles.china');
    return t('roles.staff');
  }

  const tot = data?.totals;
  const tiles: { label: string; value: React.ReactNode; tone: Tone; icon: React.ReactNode }[] = [
    { label: t('cd.clients'), value: tot?.clients, tone: 'teal', icon: <IconStaff size={19} /> },
    { label: t('cd.staff'), value: tot?.staff, tone: 'indigo', icon: <IconStaff size={19} /> },
    { label: t('cd.pickups'), value: tot?.pickups, tone: 'blue', icon: <IconWarehouse size={19} /> },
    { label: t('cd.parcels'), value: tot?.parcels, tone: 'violet', icon: <IconBox size={19} /> },
    { label: t('cd.atWarehouse'), value: tot?.at_warehouse, tone: 'amber', icon: <IconWarehouse size={19} /> },
    { label: t('cd.issued'), value: tot?.issued, tone: 'green', icon: <IconIssue size={19} /> },
    { label: t('cd.revenue'), value: tot ? money(tot.revenue_issued) : undefined, tone: 'green', icon: <IconRevenue size={19} /> },
  ];

  const pickupCols: Column<PickupRow>[] = [
    {
      key: 'pvz',
      header: t('cd.pvz'),
      sortValue: (p) => p.title,
      render: (p) => (
        <div>
          <div className="strong">{p.title}</div>
          {p.address && <div className="muted" style={{ fontSize: 12.5 }}>{p.address}</div>}
        </div>
      ),
    },
    { key: 'clients', header: t('cd.colClients'), align: 'right', sortValue: (p) => p.clients, render: (p) => <span className="num">{p.clients}</span> },
    { key: 'staff', header: t('cd.colStaff'), align: 'right', sortValue: (p) => p.staff, render: (p) => <span className="num">{p.staff}</span> },
    {
      key: 'at',
      header: t('cd.colAtWarehouse'),
      align: 'right',
      sortValue: (p) => p.at_warehouse,
      render: (p) => (p.at_warehouse ? <Badge variant="amber">{p.at_warehouse}</Badge> : <span className="num">0</span>),
    },
    { key: 'parcels', header: t('cd.colParcels'), align: 'right', sortValue: (p) => p.parcels, render: (p) => <span className="num">{p.parcels}</span> },
    { key: 'issued', header: t('cd.colIssued'), align: 'right', sortValue: (p) => p.issued, render: (p) => <span className="num">{p.issued}</span> },
    {
      key: 'status',
      header: t('common.status'),
      sortValue: (p) => (p.is_active ? 0 : 1),
      render: (p) => (
        <Badge variant={p.is_active ? 'ok' : 'warn'} dot>
          {p.is_active ? t('common.active') : t('common.inactive')}
        </Badge>
      ),
    },
  ];

  const staffCols: Column<StaffRow>[] = [
    {
      key: 'name',
      header: t('cd.name'),
      sortValue: (s) => s.full_name || s.phone,
      render: (s) => (
        <div>
          <div className="strong">{s.full_name || t('ov.noName')}</div>
          <div className="muted mono" style={{ fontSize: 12.5 }}>{s.phone}</div>
        </div>
      ),
    },
    { key: 'role', header: t('cd.role'), render: (s) => <Badge variant="plain">{roleLabel(s)}</Badge> },
    { key: 'pvz', header: t('cd.pvz'), render: (s) => <span style={{ fontSize: 13 }}>{s.pickup_point_title || '—'}</span> },
    {
      key: 'active',
      header: t('common.status'),
      sortValue: (s) => (s.is_active ? 0 : 1),
      render: (s) => (
        <Badge variant={s.is_active ? 'ok' : 'warn'} dot>
          {s.is_active ? t('common.active') : t('common.inactive')}
        </Badge>
      ),
    },
  ];

  const statusRows = Object.entries(data?.parcels_by_status ?? {}).sort((a, b) => b[1] - a[1]);

  if (err)
    return (
      <div>
        <PageHeader title={t('cd.title')} actions={<Button variant="subtle" onClick={() => nav('/overview')}>{t('cd.back')}</Button>} />
        <Alert variant="error">{err}</Alert>
      </div>
    );

  return (
    <div>
      <PageHeader
        title={loading ? t('cd.title') : data?.cargo.title || t('cd.title')}
        subtitle={
          data ? (
            <span className="cluster gap-sm">
              <span className="mono">{data.cargo.slug}</span>
              <Badge variant="blue">{money(data.cargo.price_per_kg_kgs)}/кг</Badge>
              <Badge variant={data.cargo.is_active ? 'ok' : 'warn'} dot>
                {data.cargo.is_active ? t('common.active') : t('common.inactive')}
              </Badge>
              {data.cargo.phone && <span className="muted">{data.cargo.phone}</span>}
            </span>
          ) : (
            t('cd.subtitle')
          )
        }
        actions={
          <Button variant="subtle" onClick={() => nav('/overview')} icon={<IconOverview size={18} />}>
            {t('cd.back')}
          </Button>
        }
      />

      <StatGrid className="mb-lg">
        {tiles.map((tile) => (
          <Stat
            key={tile.label}
            icon={tile.icon}
            tone={tile.tone}
            label={tile.label}
            value={tile.value === undefined ? <Skeleton height={26} width="45%" /> : tile.value}
          />
        ))}
      </StatGrid>

      <Card>
        <CardHeader
          title={t('cd.warehousesCard')}
          description={t('cd.warehousesDesc')}
          actions={data && <Badge variant="plain">{data.pickups.length} {t('cd.pvzCount')}</Badge>}
        />
        <DataTable
          columns={pickupCols}
          rows={data?.pickups}
          loading={loading}
          getRowKey={(p) => p.id}
          onRowClick={openPickup}
          initialSort={{ key: 'at', dir: 'desc' }}
          empty={<EmptyState icon={<IconWarehouse size={26} />} title={t('cd.noPvz')} description={t('cd.noPvzDesc')} />}
        />
      </Card>

      <Card className="mt-lg">
        <CardHeader title={t('cd.staffCard')} actions={data && <Badge variant="plain">{data.staff.length}</Badge>} />
        <DataTable
          columns={staffCols}
          rows={data?.staff}
          loading={loading}
          getRowKey={(s) => s.id}
          empty={<EmptyState icon={<IconStaff size={26} />} title={t('cd.noStaff')} />}
        />
      </Card>

      {statusRows.length > 0 && (
        <Card className="mt-lg">
          <CardHeader title={t('cd.byStatusCard')} />
          <div className="status-grid">
            {statusRows.map(([status, count]) => (
              <div key={status} className="status-chip">
                <Badge variant={statusMeta(status).tone} dot>{t(`status.${status}`)}</Badge>
                <span className="num strong">{count}</span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {pickupSel && (
        <PickupParcelsModal
          pickup={pickupSel}
          filter={pFilter}
          onFilter={setPFilter}
          rows={pList}
          loading={pLoading}
          error={pErr}
          onClose={() => setPickupSel(null)}
          t={t}
        />
      )}
    </div>
  );
}

function PickupParcelsModal({
  pickup,
  filter,
  onFilter,
  rows,
  loading,
  error,
  onClose,
  t,
}: {
  pickup: PickupRow;
  filter: PFilter;
  onFilter: (f: PFilter) => void;
  rows: ParcelRow[] | null;
  loading: boolean;
  error: string;
  onClose: () => void;
  t: (k: string) => string;
}) {
  const filterOptions: SegmentedOption<PFilter>[] = [
    { value: 'stock', label: t('cd.stockFilter') },
    { value: 'all', label: t('cd.allFilter') },
  ];

  const totals = useMemo(() => {
    const list = rows ?? [];
    return {
      count: list.length,
      weight: list.reduce((s, p) => s + pnum(p.weight), 0),
      price: list.reduce((s, p) => s + pnum(p.delivery_price), 0),
    };
  }, [rows]);

  const columns: Column<ParcelRow>[] = [
    { key: 'product', header: t('op.product'), render: (p) => <span className="truncate" style={{ maxWidth: 200, display: 'inline-block' }}>{p.product_title || '—'}</span> },
    { key: 'track', header: t('common.track'), render: (p) => <span className="mono">{p.track_number}</span> },
    {
      key: 'client',
      header: t('common.client'),
      render: (p) =>
        p.client_code ? (
          <div>
            <div className="strong" style={{ fontSize: 13 }}>{p.client_name || '—'}</div>
            <div className="muted mono" style={{ fontSize: 12 }}>{p.client_code}</div>
          </div>
        ) : (
          <Badge variant="warn">{t('common.noClient')}</Badge>
        ),
    },
    { key: 'status', header: t('common.status'), render: (p) => <Badge variant={statusMeta(p.status).tone} dot>{t(`status.${p.status}`)}</Badge> },
    { key: 'weight', header: t('op.weightKg'), align: 'right', render: (p) => <span className="num">{p.weight ?? '—'}</span> },
    { key: 'price', header: t('op.price'), align: 'right', render: (p) => <span className="num">{money(p.delivery_price)}</span> },
  ];

  return (
    <Modal
      title={pickup.title}
      description={pickup.address || undefined}
      onClose={onClose}
      footer={
        <div className="cluster gap-sm" style={{ width: '100%' }}>
          <Badge variant="plain">{totals.count} {t('wh.pcs')}</Badge>
          <Badge variant="violet">{totals.weight.toFixed(2)} кг</Badge>
          <Badge variant="green">{money(totals.price)}</Badge>
          <span className="grow" />
          <Button variant="subtle" onClick={onClose}>{t('common.cancel')}</Button>
        </div>
      }
    >
      <div className="cluster" style={{ marginBottom: 12 }}>
        <Segmented options={filterOptions} value={filter} onChange={onFilter} ariaLabel={t('common.status')} />
      </div>
      {error ? (
        <Alert variant="error">{error}</Alert>
      ) : (
        <DataTable
          columns={columns}
          rows={rows}
          loading={loading}
          getRowKey={(p) => p.id}
          empty={<EmptyState icon={<IconBox size={26} />} title={t('cd.pvzEmpty')} description={filter === 'stock' ? t('cd.pvzEmptyStock') : t('cd.pvzEmptyAll')} />}
        />
      )}
    </Modal>
  );
}
