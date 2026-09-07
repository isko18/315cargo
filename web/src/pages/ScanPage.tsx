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
  useToast,
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

/**
 * Строка сессии приёмки. Скан попадает в список сразу, до ответа сервера:
 * оператор сканирует коробки подряд, и ждать сеть на каждой нельзя.
 */
type Row =
  | { id: string; state: 'pending'; track: string }
  | { id: string; state: 'error'; track: string; message: string }
  | { id: string; state: 'done'; track: string; entry: Entry };

type Job = { id: string; track: string; weight: string; cargo: string; pickup: number | null };

let rowSeq = 0;

export default function ScanPage() {
  const { t } = useI18n();
  const toast = useToast();
  const { points, activeId } = usePickup();
  const activePoint = points.find((p) => p.id === activeId);
  // «Карго ID» нужен только супер-админу (у него нет своего карго). У обычного
  // оператора/админа карго берётся из аккаунта — поле не показываем.
  const isSuper = Boolean(getRole().is_superuser);
  const [view, setView] = useState<'scan' | 'history'>('scan');
  const [track, setTrack] = useState('');
  const [weight, setWeight] = useState('');
  const [cargo, setCargo] = useState('');
  const [err, setErr] = useState('');
  const [rows, setRows] = useState<Row[]>([]);
  const [queued, setQueued] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  // Очередь в ref: воркер читает её синхронно, лишние перерисовки на каждый
  // скан только тормозили бы ввод.
  const queueRef = useRef<Job[]>([]);
  const runningRef = useRef(false);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  /** Отправляет очередь по одной, сохраняя порядок сканирования. */
  async function drain() {
    if (runningRef.current) return;
    runningRef.current = true;
    try {
      while (queueRef.current.length > 0) {
        const job = queueRef.current[0];
        try {
          const body: Record<string, unknown> = { track_number: job.track, status: RECEIVE_STATUS };
          if (job.weight) body.weight = job.weight;
          if (job.cargo) body.cargo = Number(job.cargo);
          // Активный ПВЗ — бэкенд запишет его адрес при статусе «В ПВЗ».
          if (job.pickup) body.pickup_point = job.pickup;
          const entry = await post<Entry>('/api/parcels/scan/', body);
          setRows((rs) =>
            rs.map((r) => (r.id === job.id ? { id: job.id, state: 'done', track: job.track, entry } : r)),
          );
        } catch (e) {
          const msg = (e as ApiError).message;
          setRows((rs) =>
            rs.map((r) => (r.id === job.id ? { id: job.id, state: 'error', track: job.track, message: msg } : r)),
          );
          setErr(msg);
          // Тост только на ошибку: успех виден строкой, а при быстром
          // сканировании поток тостов перекрыл бы саму таблицу.
          toast.error(t('toast.error'), `${job.track} · ${msg}`);
        }
        queueRef.current.shift();
        setQueued(queueRef.current.length);
      }
    } finally {
      runningRef.current = false;
    }
  }

  /** Скан не ждёт сеть: строка появляется сразу, отправка идёт фоном. */
  function scan(codeArg?: string) {
    const tn = (codeArg ?? track).trim();
    if (!tn) return;
    // Сканер иногда срабатывает дважды на одной коробке — дубль не плодим.
    if (queueRef.current.some((j) => j.track === tn)) {
      setTrack('');
      return;
    }
    setErr('');
    const id = `r${++rowSeq}`;
    setRows((rs) => [{ id, state: 'pending', track: tn }, ...rs]);
    // Вес и карго фиксируем на момент скана: оператор успеет их поменять,
    // пока очередь разгребается.
    queueRef.current.push({
      id,
      track: tn,
      weight: weight.trim(),
      cargo: cargo.trim(),
      pickup: activeId,
    });
    setQueued(queueRef.current.length);
    setTrack('');
    setWeight('');
    inputRef.current?.focus();
    void drain();
  }

  /** Повторная отправка упавшей строки — без пересканирования коробки. */
  function retry(id: string, tn: string) {
    setRows((rs) => rs.map((r) => (r.id === id ? { id, state: 'pending', track: tn } : r)));
    queueRef.current.push({ id, track: tn, weight: '', cargo: cargo.trim(), pickup: activeId });
    setQueued(queueRef.current.length);
    void drain();
  }

  // Глобальный перехват штрих-сканера — работает без клика в поле.
  useBarcodeScanner((code) => {
    setTrack(code);
    scan(code);
  });

  /** Заменяет посылку в подтверждённой строке — общее для веса и привязки. */
  function replaceParcel(parcelId: number, parcel: Parcel) {
    setRows((rs) =>
      rs.map((r) =>
        r.state === 'done' && r.entry.parcel.id === parcelId
          ? { ...r, entry: { ...r.entry, parcel } }
          : r,
      ),
    );
  }

  async function assign(entryId: number, clientCode: string) {
    const cc = clientCode.trim();
    if (!cc) return;
    setErr('');
    try {
      const updated = await post<Parcel>(`/api/parcels/${entryId}/assign/`, { client_code: cc });
      replaceParcel(entryId, updated);
      toast.success(t('toast.assignOk'), `${updated.track_number} → ${cc}`);
    } catch (e) {
      const msg = (e as ApiError).message;
      setErr(msg);
      toast.error(t('toast.error'), msg);
    }
  }

  // Уточнение веса уже принятой посылки (после скана) — цена пересчитывается.
  async function saveWeight(entryId: number, w: string) {
    setErr('');
    try {
      const updated = await post<Parcel>(`/api/parcels/${entryId}/weight/`, {
        weight: w === '' ? null : w,
      });
      replaceParcel(entryId, updated);
    } catch (e) {
      const msg = (e as ApiError).message;
      setErr(msg);
      toast.error(t('toast.error'), msg);
      throw e;
    }
  }

  const done = rows.filter((r): r is Extract<Row, { state: 'done' }> => r.state === 'done');
  const withWeight = done.filter((r) => r.entry.parcel.weight).length;
  const failed = rows.filter((r) => r.state === 'error').length;

  const columns: Column<Row>[] = [
    {
      key: 'track',
      header: t('common.track'),
      mobile: 'title',
      render: (r) => (
        <span className="mono strong" translate="no">
          {r.state === 'done' ? r.entry.parcel.track_number : r.track}
        </span>
      ),
    },
    {
      key: 'result',
      header: t('common.result'),
      render: (r) =>
        r.state === 'pending' ? (
          <Badge variant="plain">{t('china.sending')}</Badge>
        ) : r.state === 'error' ? (
          <Badge variant="red">{t('china.failed')}</Badge>
        ) : (
          <Badge variant={RESULT_TONE[r.entry.result] ?? 'gray'}>{t(`result.${r.entry.result}`)}</Badge>
        ),
    },
    {
      key: 'status',
      header: t('common.status'),
      render: (r) =>
        r.state === 'done' ? (
          <Badge variant={statusMeta(r.entry.parcel.status).tone} dot>
            {t(`status.${r.entry.parcel.status}`)}
          </Badge>
        ) : r.state === 'error' ? (
          <span className="muted" style={{ fontSize: 13 }}>{r.message}</span>
        ) : (
          <span className="muted" style={{ fontSize: 13 }}>—</span>
        ),
    },
    {
      key: 'weight',
      header: t('op.weightKg'),
      align: 'right',
      // Вес правится только у подтверждённой посылки: у неё есть id на сервере.
      render: (r) =>
        r.state === 'done' ? (
          <WeightInline value={r.entry.parcel.weight} onSave={(w) => saveWeight(r.entry.parcel.id, w)} />
        ) : (
          <span className="muted">—</span>
        ),
    },
    {
      key: 'price',
      header: t('op.price'),
      align: 'right',
      render: (r) =>
        r.state === 'done' ? (
          <span className="num">{money(r.entry.parcel.delivery_price)}</span>
        ) : (
          <span className="muted">—</span>
        ),
    },
    {
      key: 'client',
      header: t('common.client'),
      render: (r) => {
        if (r.state === 'error') {
          // Повтор прямо из строки: искать коробку и сканировать заново не нужно.
          return (
            <Button variant="subtle" size="sm" onClick={() => retry(r.id, r.track)}>
              {t('china.retry')}
            </Button>
          );
        }
        if (r.state !== 'done') return <span className="muted">—</span>;
        return r.entry.parcel.user ? (
          <Badge variant="ok" className="mono">{r.entry.parcel.client_code}</Badge>
        ) : (
          <AssignInline onAssign={(cc) => assign(r.entry.parcel.id, cc)} t={t} />
        );
      },
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
        <OperationHistory type="receive" reloadSignal={done.length} />
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
            <Button onClick={() => scan()} disabled={!track.trim()} icon={<IconCheck size={18} />}>
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
              <Badge variant="plain">{rows.length} {t('wh.pcs')}</Badge>
              {queued > 0 && <Badge variant="blue" dot>{queued} {t('china.inQueue')}</Badge>}
              {failed > 0 && <Badge variant="red">{failed} {t('china.failed')}</Badge>}
              {withWeight > 0 && <Badge variant="ok">{withWeight} {t('scan.withWeight')}</Badge>}
            </div>
          }
        />
        <DataTable
          columns={columns}
          rows={rows}
          getRowKey={(r) => r.id}
          rowClassName={(r) => (r.state === 'pending' ? 'row-dim' : undefined)}
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
