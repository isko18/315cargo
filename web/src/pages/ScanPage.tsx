import { useEffect, useRef, useState } from 'react';
import { money } from '../money';
import { ApiError, getRole, post } from '../api';
import { statusMeta } from '../status';
import { useI18n } from '../i18n';
import { usePickup } from '../pickupContext';
import { useBarcodeScanner } from '../useBarcodeScanner';
import WeightInline from '../components/WeightInline';
import OperationHistory from '../components/OperationHistory';
import ClientSearch from '../components/ClientSearch';
import { IconScan, IconCheck, IconBox } from '../components/Icons';
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

// Приём на стороне карго = 2-й скан = прибытие в ПВЗ. Промежуточные статусы
// (в пути, прибыл в КР и т.п.) ставятся автоматически, вручную не выбираются.
const RECEIVE_STATUS = 'at_pickup_point';

const RESULT_TONE: Record<string, 'blue' | 'green' | 'amber' | 'gray'> = {
  updated: 'blue',
  unchanged: 'gray',
  created_from_order: 'green',
  created_pending: 'amber',
};

type Parcel = {
  id: number;
  track_number: string;
  status: string;
  status_display_name: string;
  client_code: string | null;
  user: number | null;
  weight: string | null;
  delivery_price: string | null;
};

type Entry = { result: string; parcel: Parcel };

export default function ScanPage() {
  const { t } = useI18n();
  const { points, activeId } = usePickup();
  const activePoint = points.find((p) => p.id === activeId);
  // «Карго ID» нужен только супер-админу (у него нет своего карго). У обычного
  // оператора/админа карго берётся из аккаунта — поле не показываем.
  const isSuper = Boolean(getRole().is_superuser);
  const [view, setView] = useState<'scan' | 'history'>('scan');
  const [track, setTrack] = useState('');
  const [weight, setWeight] = useState('');
  const [cargo, setCargo] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [log, setLog] = useState<Entry[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  async function scan(codeArg?: string) {
    const tn = (codeArg ?? track).trim();
    if (!tn || busy) return;
    setErr('');
    setBusy(true);
    try {
      const body: Record<string, unknown> = { track_number: tn, status: RECEIVE_STATUS };
      if (weight.trim()) body.weight = weight.trim();
      if (cargo.trim()) body.cargo = Number(cargo.trim());
      // Активный ПВЗ (переключатель) — бэкенд запишет его адрес при статусе «В ПВЗ».
      if (activeId) body.pickup_point = activeId;
      const r = await post<Entry>('/api/parcels/scan/', body);
      setLog((l) => [r, ...l]);
      setTrack('');
      setWeight('');
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  }

  // Глобальный перехват штрих-сканера — работает без клика в поле.
  useBarcodeScanner((code) => {
    setTrack(code);
    scan(code);
  });

  async function assign(entryId: number, clientCode: string) {
    const cc = clientCode.trim();
    if (!cc) return;
    const entry = log.find((e) => e.parcel.id === entryId);
    if (!entry) return;
    setErr('');
    try {
      const updated = await post<Parcel>(`/api/parcels/${entryId}/assign/`, { client_code: cc });
      setLog((l) => l.map((e) => (e.parcel.id === entryId ? { ...e, parcel: updated } : e)));
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  // Уточнение веса уже принятой посылки (после скана) — цена пересчитывается.
  async function saveWeight(entryId: number, w: string) {
    setErr('');
    try {
      const updated = await post<Parcel>(`/api/parcels/${entryId}/weight/`, {
        weight: w === '' ? null : w,
      });
      setLog((l) => l.map((e) => (e.parcel.id === entryId ? { ...e, parcel: updated } : e)));
    } catch (e) {
      setErr((e as ApiError).message);
      throw e;
    }
  }

  const withWeight = log.filter((e) => e.parcel.weight).length;

  const columns: Column<Entry>[] = [
    { key: 'track', header: t('common.track'), render: (e) => <span className="mono strong">{e.parcel.track_number}</span> },
    {
      key: 'result',
      header: t('common.result'),
      render: (e) => <Badge variant={RESULT_TONE[e.result] ?? 'gray'}>{t(`result.${e.result}`)}</Badge>,
    },
    {
      key: 'status',
      header: t('common.status'),
      render: (e) => (
        <Badge variant={statusMeta(e.parcel.status).tone} dot>
          {t(`status.${e.parcel.status}`)}
        </Badge>
      ),
    },
    {
      key: 'weight',
      header: t('op.weightKg'),
      align: 'right',
      render: (e) => (
        <WeightInline value={e.parcel.weight} onSave={(w) => saveWeight(e.parcel.id, w)} />
      ),
    },
    {
      key: 'price',
      header: t('op.price'),
      align: 'right',
      render: (e) => <span className="num">{money(e.parcel.delivery_price)}</span>,
    },
    {
      key: 'client',
      header: t('common.client'),
      render: (e) =>
        e.parcel.user ? (
          <Badge variant="ok" className="mono">{e.parcel.client_code}</Badge>
        ) : (
          <AssignInline onAssign={(cc) => assign(e.parcel.id, cc)} t={t} />
        ),
    },
  ];

  const tabOptions: SegmentedOption<'scan' | 'history'>[] = [
    { value: 'scan', label: t('nav.scan') },
    { value: 'history', label: t('hist.tab') },
  ];

  return (
    <div>
      <PageHeader title={t('scan.title')} subtitle={t('scan.subtitle')} />

      <div className="mb-lg">
        <Segmented options={tabOptions} value={view} onChange={setView} ariaLabel={t('hist.tab')} />
      </div>

      {view === 'history' ? (
        <OperationHistory type="receive" reloadSignal={log.length} />
      ) : (
      <>
      <Card>
        <CardHeader
          title={t('scan.cardTitle')}
          description={t('scan.cardDesc')}
          actions={
            <div className="cluster gap-sm">
              <Badge variant="violet" dot>{t('status.at_pickup_point')}</Badge>
              {activePoint ? (
                <Badge variant="plain">{activePoint.title}</Badge>
              ) : (
                <Badge variant="warn">{t('scan.pvzAuto')}</Badge>
              )}
            </div>
          }
        />
        <CardBody>
          <div className="row">
            <Field label={t('scan.trackLabel')} style={{ flex: 3 }}>
              <Input
                ref={inputRef}
                className="scan-input"
                icon={<IconScan size={18} />}
                value={track}
                onChange={(e) => setTrack(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && scan()}
                placeholder={t('scan.trackPlaceholder')}
                autoComplete="off"
              />
            </Field>
            <Field label={t('op.weight')} style={{ flex: 1, minWidth: 140 }}>
              <Input
                type="number"
                min="0"
                step="0.001"
                inputMode="decimal"
                suffix="кг"
                value={weight}
                onChange={(e) => setWeight(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && scan()}
                placeholder={t('scan.weightPlaceholder')}
              />
            </Field>
            <Button onClick={() => scan()} loading={busy} disabled={!track.trim()} icon={<IconCheck size={18} />}>
              {t('scan.accept')}
            </Button>
          </div>

          {isSuper && (
            <Field label={t('op.cargoId')} helper={t('op.cargoIdHelperSuper')} className="mt-md" style={{ maxWidth: 340 }}>
              <Input value={cargo} onChange={(e) => setCargo(e.target.value)} placeholder="1" />
            </Field>
          )}

          {err && <Alert variant="error">{err}</Alert>}
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title={t('scan.session')}
          actions={
            <div className="cluster gap-sm">
              <Badge variant="plain">{log.length} {t('wh.pcs')}</Badge>
              {withWeight > 0 && <Badge variant="ok">{withWeight} {t('scan.withWeight')}</Badge>}
            </div>
          }
        />
        <DataTable
          columns={columns}
          rows={log}
          getRowKey={(e) => e.parcel.id}
          empty={<EmptyState icon={<IconBox size={26} />} title={t('scan.emptyTitle')} description={t('scan.emptyDesc')} />}
        />
      </Card>
      </>
      )}
    </div>
  );
}

function AssignInline({ onAssign, t }: { onAssign: (code: string) => void; t: (k: string) => string }) {
  return (
    <div style={{ minWidth: 210 }}>
      <ClientSearch
        size="sm"
        placeholder={t('scan.assignPlaceholder')}
        onPick={(c) => onAssign(c.client_code)}
      />
    </div>
  );
}
