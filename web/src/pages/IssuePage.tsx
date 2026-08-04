import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { ApiError, get, getRole, post } from '../api';

// html5-qrcode тяжёлый — грузим сканер отдельным чанком только при открытии.
const QrScanner = lazy(() => import('../components/QrScanner'));
import { FINAL, statusMeta } from '../status';
import { useI18n } from '../i18n';
import WeightInline from '../components/WeightInline';
import OperationHistory from '../components/OperationHistory';
import ClientSearch from '../components/ClientSearch';
import { IconCamera, IconIssue, IconBox } from '../components/Icons';
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
  Input,
  PageHeader,
  Segmented,
  type SegmentedOption,
} from '../ui';

type Parcel = {
  id: number;
  track_number: string;
  status: string;
  status_display_name: string;
  client_code: string | null;
  product_title?: string | null;
  product_image?: string | null;
  weight: string | null;
  delivery_price: string | null;
};

const READY = 'at_pickup_point'; // «к выдаче» — прибыл в ПВЗ
type FilterKey = 'ready' | 'active' | 'all';

const num = (v?: string | null) => (v ? parseFloat(v) || 0 : 0);

export default function IssuePage() {
  const { t } = useI18n();
  // «Карго ID» — только для супер-админа без своего карго.
  const isSuper = Boolean(getRole().is_superuser);
  const [tab, setTab] = useState<'issue' | 'history'>('issue');
  const [clientCode, setClientCode] = useState('');
  const [debounced, setDebounced] = useState('');
  const [cargo, setCargo] = useState('');
  const [parcels, setParcels] = useState<Parcel[] | null>(null);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [filter, setFilter] = useState<FilterKey>('ready');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [issuedTick, setIssuedTick] = useState(0); // обновляет историю выдач
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const [scanning, setScanning] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Live-поиск: печатаешь код — результаты подгружаются на лету.
  useEffect(() => {
    const h = setTimeout(() => setDebounced(clientCode.trim()), 350);
    return () => clearTimeout(h);
  }, [clientCode]);

  useEffect(() => {
    if (debounced.length < 3) {
      setParcels(null);
      setSel(new Set());
      return;
    }
    let cancelled = false;
    setLoading(true);
    setErr('');
    setMsg('');
    get(`/api/parcels/?client_code=${encodeURIComponent(debounced)}`)
      .then((data: any) => {
        if (cancelled) return;
        const list = (data?.results ?? data) as Parcel[];
        setParcels(list);
        // По умолчанию выбираем то, что реально к выдаче.
        setSel(new Set(list.filter((p) => p.status === READY).map((p) => p.id)));
      })
      .catch((e) => {
        if (cancelled) return;
        setErr((e as ApiError).message);
        setParcels(null);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [debounced]);

  function onQr(text: string) {
    setScanning(false);
    setClientCode(text);
  }

  // Вес на выдаче: сохраняем и обновляем строку (бэкенд пересчитывает цену),
  // чтобы итог «К оплате» сразу учитывал уточнённый вес.
  async function saveWeight(id: number, w: string) {
    setErr('');
    try {
      const updated = await post<Parcel>(`/api/parcels/${id}/weight/`, {
        weight: w === '' ? null : w,
      });
      setParcels((list) => (list ? list.map((p) => (p.id === id ? updated : p)) : list));
    } catch (e) {
      setErr((e as ApiError).message);
      throw e;
    }
  }

  const view = useMemo(() => {
    const rows = parcels ?? [];
    if (filter === 'ready') return rows.filter((p) => p.status === READY);
    if (filter === 'active') return rows.filter((p) => !FINAL.has(p.status));
    return rows;
  }, [parcels, filter]);

  const selectableInView = view.filter((p) => !FINAL.has(p.status));
  const allSelected = selectableInView.length > 0 && selectableInView.every((p) => sel.has(p.id));

  function toggle(id: number) {
    setSel((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  }
  function toggleAll() {
    setSel((s) => {
      const n = new Set(s);
      if (allSelected) selectableInView.forEach((p) => n.delete(p.id));
      else selectableInView.forEach((p) => n.add(p.id));
      return n;
    });
  }

  const selectedParcels = (parcels ?? []).filter((p) => sel.has(p.id));
  const totals = {
    count: selectedParcels.length,
    weight: selectedParcels.reduce((s, p) => s + num(p.weight), 0),
    price: selectedParcels.reduce((s, p) => s + num(p.delivery_price), 0),
  };

  async function issue() {
    if (!parcels || sel.size === 0 || busy) return;
    setErr('');
    setMsg('');
    setBusy(true);
    const chosen = parcels.filter((p) => sel.has(p.id) && !FINAL.has(p.status));
    let ok = 0;
    const errors: string[] = [];
    for (const p of chosen) {
      try {
        const body: Record<string, unknown> = { track_number: p.track_number, status: 'issued' };
        if (cargo.trim()) body.cargo = Number(cargo.trim());
        await post('/api/parcels/scan/', body);
        ok += 1;
      } catch (e) {
        errors.push(`${p.track_number}: ${(e as ApiError).message}`);
      }
    }
    setMsg(`${t('issue.done')}: ${ok} / ${chosen.length} · $${totals.price.toFixed(2)}`);
    if (errors.length) setErr(errors.join('\n'));
    setBusy(false);
    if (ok > 0) setIssuedTick((n) => n + 1); // обновить историю выдач
    // Перезагрузка текущего клиента, чтобы обновить статусы.
    try {
      const data: any = await get(`/api/parcels/?client_code=${encodeURIComponent(debounced)}`);
      const list = (data?.results ?? data) as Parcel[];
      setParcels(list);
      setSel(new Set(list.filter((p) => p.status === READY).map((p) => p.id)));
    } catch {
      /* ignore */
    }
  }

  const filterOptions: SegmentedOption<FilterKey>[] = [
    { value: 'ready', label: t('issue.filterReady') },
    { value: 'active', label: t('issue.filterActive') },
    { value: 'all', label: t('issue.filterAll') },
  ];

  const columns: Column<Parcel>[] = [
    {
      key: 'sel',
      width: 44,
      header: (
        <input
          type="checkbox"
          className="tbl-check"
          aria-label={t('issue.selectAll')}
          checked={allSelected}
          disabled={selectableInView.length === 0}
          onChange={toggleAll}
        />
      ),
      render: (p) => (
        <input
          type="checkbox"
          className="tbl-check"
          disabled={FINAL.has(p.status)}
          checked={sel.has(p.id)}
          onChange={() => toggle(p.id)}
        />
      ),
    },
    {
      key: 'product',
      header: t('op.product'),
      render: (p) => (
        <div className="cell-product">
          {p.product_image ? (
            <img src={p.product_image} alt="" className="thumb" />
          ) : (
            <span className="thumb thumb-fallback">
              <IconBox size={20} />
            </span>
          )}
          <span className="strong truncate" style={{ maxWidth: 220 }}>
            {p.product_title || '—'}
          </span>
        </div>
      ),
    },
    { key: 'track', header: t('common.track'), render: (p) => <span className="mono">{p.track_number}</span> },
    {
      key: 'weight',
      header: t('op.weightKg'),
      align: 'right',
      render: (p) =>
        FINAL.has(p.status) ? (
          <span className="num">{p.weight ?? '—'}</span>
        ) : (
          <WeightInline value={p.weight} onSave={(w) => saveWeight(p.id, w)} />
        ),
    },
    {
      key: 'price',
      header: t('op.priceUsd'),
      align: 'right',
      render: (p) => <span className="num">{p.delivery_price ? `$${p.delivery_price}` : '—'}</span>,
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
  ];

  const readyCount = (parcels ?? []).filter((p) => p.status === READY).length;

  const tabOptions: SegmentedOption<'issue' | 'history'>[] = [
    { value: 'issue', label: t('nav.issue') },
    { value: 'history', label: t('hist.tab') },
  ];

  return (
    <div>
      <PageHeader title={t('issue.title')} subtitle={t('issue.subtitle')} />

      <div className="mb-lg">
        <Segmented options={tabOptions} value={tab} onChange={setTab} ariaLabel={t('hist.tab')} />
      </div>

      {scanning && (
        <Suspense fallback={null}>
          <QrScanner onResult={onQr} onClose={() => setScanning(false)} />
        </Suspense>
      )}

      {tab === 'history' ? (
        <OperationHistory type="issue" reloadSignal={issuedTick} />
      ) : (
      <>
      <Card>
        <CardHeader title={t('issue.findCard')} description={t('issue.findCardDesc')} />
        <CardBody>
          <div className="row">
            <Field label={t('issue.clientCodeLabel')} helper={t('issue.searchHint')} style={{ flex: 3 }}>
              <ClientSearch
                autoFocus
                placeholder={t('clientsearch.placeholder')}
                onPick={(c) => setClientCode(c.client_code)}
              />
            </Field>
            <Button variant="secondary" onClick={() => setScanning(true)} disabled={busy} icon={<IconCamera size={18} />}>
              {t('issue.scanQr')}
            </Button>
          </div>

          {isSuper && (
            <Field label={t('op.cargoId')} helper={t('op.cargoIdHelperSuperShort')} className="mt-md" style={{ maxWidth: 340 }}>
              <Input value={cargo} onChange={(e) => setCargo(e.target.value)} placeholder="1" />
            </Field>
          )}

          {err && <Alert variant="error" className="prewrap">{err}</Alert>}
          {msg && <Alert variant="success">{msg}</Alert>}
        </CardBody>
      </Card>

      {parcels && (
        <Card>
          <CardHeader
            title={t('issue.parcelsCard')}
            actions={
              <div className="cluster gap-sm">
                <Segmented options={filterOptions} value={filter} onChange={setFilter} ariaLabel={t('common.status')} />
                <Badge variant="ok">{readyCount} {t('issue.toIssue')}</Badge>
              </div>
            }
          />
          <DataTable
            columns={columns}
            rows={view}
            loading={loading}
            getRowKey={(p) => p.id}
            rowClassName={(p) => (FINAL.has(p.status) ? 'row-dim' : undefined)}
            empty={
              parcels.length === 0 ? (
                <EmptyState icon={<IconBox size={26} />} title={t('issue.emptyTitle')} description={t('issue.emptyDesc')} />
              ) : (
                <EmptyState icon={<IconBox size={26} />} title={t('issue.nothingTitle')} description={t('issue.nothingDesc')} />
              )
            }
          />

          {/* Панель итогов выдачи */}
          <div className="issue-bar">
            <div className="metric">
              <span className="m-val">{totals.count}</span>
              <span className="m-lbl">{t('issue.selected')}</span>
            </div>
            <div className="metric">
              <span className="m-val">{totals.weight.toFixed(2)} кг</span>
              <span className="m-lbl">{t('issue.weight')}</span>
            </div>
            <div className="metric total">
              <span className="m-val">${totals.price.toFixed(2)}</span>
              <span className="m-lbl">{t('issue.toPay')}</span>
            </div>
            <span className="grow" />
            <Button onClick={issue} loading={busy} disabled={sel.size === 0} icon={<IconIssue size={18} />} style={{ padding: '11px 20px' }}>
              {t('issue.issueBtn')} ({sel.size})
            </Button>
          </div>
        </Card>
      )}
      </>
      )}
    </div>
  );
}
