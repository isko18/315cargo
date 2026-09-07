import { useEffect, useRef, useState } from 'react';
import { ApiError, post } from '../api';
import { statusMeta, type Tone } from '../status';
import { useI18n } from '../i18n';
import { useBarcodeScanner } from '../useBarcodeScanner';
import { IconScan, IconCheck, IconGlobe, IconClose } from '../components/Icons';
import OperationHistory from '../components/OperationHistory';
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

// Со склада в Китае приёмка всегда в одном статусе.
const CHINA_STATUS = 'arrived_china_warehouse';

const RESULT_TONE: Record<string, Tone> = {
  updated: 'blue',
  unchanged: 'gray',
  created_from_order: 'green',
  created_manual: 'teal',
  created_pending: 'amber',
};

type Parcel = {
  id: number;
  track_number: string;
  status: string;
  status_display_name: string;
  client_code: string | null;
  user: number | null;
};
type Entry = { result: string; parcel: Parcel };

/**
 * Строка сессии. Скан попадает в список сразу, ещё до ответа сервера:
 * оператор на складе сканирует подряд, и ждать сеть на каждой коробке нельзя.
 */
type Row =
  | { id: string; state: 'pending'; track: string }
  | { id: string; state: 'error'; track: string; message: string }
  | { id: string; state: 'done'; track: string; entry: Entry };

type Job = { id: string; track: string; clientCode: string };

let rowSeq = 0;

export default function ChinaPage() {
  const { t } = useI18n();
  const toast = useToast();
  const [tab, setTab] = useState<'china' | 'history'>('china');
  const [track, setTrack] = useState('');
  const [clientCode, setClientCode] = useState('');
  const [err, setErr] = useState('');
  const [rows, setRows] = useState<Row[]>([]);
  const [queued, setQueued] = useState(0);
  const [flashId, setFlashId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  // Очередь в ref, а не в state: воркер читает её синхронно, и лишние
  // перерисовки на каждый скан только тормозили бы ввод.
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
          const body: Record<string, unknown> = { track_number: job.track, status: CHINA_STATUS };
          if (job.clientCode) body.client_code = job.clientCode;
          const entry = await post<Entry>('/api/parcels/scan/', body);
          setRows((rs) =>
            rs.map((r) => (r.id === job.id ? { id: job.id, state: 'done', track: job.track, entry } : r)),
          );
          setFlashId(job.id);
          window.setTimeout(() => setFlashId((cur) => (cur === job.id ? null : cur)), 1400);
        } catch (e) {
          const message = (e as ApiError).message;
          setRows((rs) =>
            rs.map((r) => (r.id === job.id ? { id: job.id, state: 'error', track: job.track, message } : r)),
          );
          setErr(message);
          // Тост только на ошибку: на успехе строка уже всё показала, а при
          // быстром сканировании поток тостов перекрыл бы саму таблицу.
          toast.error(t('toast.error'), `${job.track} · ${message}`);
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
    // Сканер иногда дублирует срабатывание — тот же трек в очереди не плодим.
    if (queueRef.current.some((j) => j.track === tn)) {
      setTrack('');
      return;
    }
    setErr('');
    const id = `r${++rowSeq}`;
    setRows((rs) => [{ id, state: 'pending', track: tn }, ...rs]);
    queueRef.current.push({ id, track: tn, clientCode: clientCode.trim() });
    setQueued(queueRef.current.length);
    setTrack('');
    inputRef.current?.focus();
    void drain();
  }

  /** Повторная отправка упавшей строки — без пересканирования коробки. */
  function retry(id: string, tn: string) {
    setRows((rs) => rs.map((r) => (r.id === id ? { id, state: 'pending', track: tn } : r)));
    queueRef.current.push({ id, track: tn, clientCode: clientCode.trim() });
    setQueued(queueRef.current.length);
    void drain();
  }

  // Глобальный перехват штрих-сканера — код подхватывается без клика в поле.
  useBarcodeScanner((code) => {
    setTrack(code);
    scan(code);
  });

  // Сводка сессии по типу приёмки — только по подтверждённым сервером.
  const done = rows.filter((r): r is Extract<Row, { state: 'done' }> => r.state === 'done');
  const counts = {
    order: done.filter((r) => r.entry.result === 'created_from_order').length,
    manual: done.filter((r) => r.entry.result === 'created_manual').length,
    unclaimed: done.filter((r) => r.entry.result === 'created_pending').length,
    failed: rows.filter((r) => r.state === 'error').length,
  };

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
      key: 'client',
      header: t('common.client'),
      render: (r) => {
        if (r.state !== 'done') return <span className="muted">—</span>;
        return r.entry.parcel.user ? (
          <Badge variant="ok" className="mono">{r.entry.parcel.client_code}</Badge>
        ) : (
          <Badge variant="warn">{t('common.noClient')}</Badge>
        );
      },
    },
    {
      key: 'retry',
      header: '',
      align: 'right',
      cardLabel: '',
      render: (r) =>
        r.state === 'error' ? (
          // Повтор прямо из строки: иначе оператору пришлось бы искать коробку
          // и сканировать её заново.
          <Button variant="subtle" size="sm" onClick={() => retry(r.id, r.track)}>
            {t('china.retry')}
          </Button>
        ) : null,
    },
  ];

  return (
    <div>
      <PageHeader title={t('china.title')} subtitle={t('china.subtitle')} />

      <div className="mb-lg">
        <Segmented
          options={[
            { value: 'china', label: t('nav.china') },
            { value: 'history', label: t('hist.tab') },
          ] as SegmentedOption<'china' | 'history'>[]}
          value={tab}
          onChange={setTab}
          ariaLabel={t('hist.tab')}
        />
      </div>

      {tab === 'history' ? (
        <OperationHistory type="china" reloadSignal={done.length} />
      ) : (
      <>
      <Card>
        <CardHeader
          title={t('china.cardTitle')}
          description={t('china.cardDesc')}
          actions={<Badge variant="amber" dot>{t('status.arrived_china_warehouse')}</Badge>}
        />
        <CardBody>
          {/* Трек — главное поле, на всю ширину */}
          <Field label={t('china.trackLabel')}>
            <Input
              ref={inputRef}
              className="scan-big"
              icon={<IconScan size={20} />}
              value={track}
              onChange={(e) => setTrack(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && scan()}
              placeholder={t('china.trackPlaceholder')}
              autoComplete="off"
            />
          </Field>

          <div className="row mt-md" style={{ alignItems: 'flex-end' }}>
            <Field
              label={t('china.clientCode')}
              helper={clientCode ? t('china.codeSticky') : t('china.clientCodeHelper')}
              style={{ flex: 1, minWidth: 200 }}
            >
              <Input
                value={clientCode}
                onChange={(e) => setClientCode(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && scan()}
                placeholder={t('china.clientCodePlaceholder')}
                autoComplete="off"
                suffix={
                  clientCode ? (
                    <button
                      type="button"
                      className="input-x"
                      onClick={() => setClientCode('')}
                      aria-label={t('china.clearCode')}
                      title={t('china.clearCode')}
                    >
                      <IconClose size={15} />
                    </button>
                  ) : undefined
                }
              />
            </Field>
            <Button onClick={() => scan()} disabled={!track.trim()} icon={<IconCheck size={18} />}>
              {t('china.accept')}
            </Button>
          </div>

          <Alert variant="info" icon={<IconGlobe size={18} />} className="mt-md">
            {t('china.shared')}
          </Alert>

          {err && <Alert variant="error">{err}</Alert>}
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title={t('china.sessionTitle')}
          actions={
            <div className="cluster gap-sm">
              <Badge variant="plain">{rows.length} {t('common.pcs')}</Badge>
              {queued > 0 && <Badge variant="blue" dot>{queued} {t('china.inQueue')}</Badge>}
              {counts.failed > 0 && <Badge variant="red">{counts.failed} {t('china.failed')}</Badge>}
              {counts.order > 0 && <Badge variant="green">{counts.order} {t('china.chipOrder')}</Badge>}
              {counts.manual > 0 && <Badge variant="teal">{counts.manual} {t('china.chipManual')}</Badge>}
              {counts.unclaimed > 0 && <Badge variant="amber">{counts.unclaimed} {t('china.chipUnclaimed')}</Badge>}
              {rows.length > 0 && (
                <Button
                  variant="subtle"
                  size="sm"
                  disabled={queued > 0}
                  onClick={() => { setRows([]); setFlashId(null); }}
                >
                  {t('china.clear')}
                </Button>
              )}
            </div>
          }
        />
        <DataTable
          columns={columns}
          rows={rows}
          getRowKey={(r) => r.id}
          rowClassName={(r) =>
            [r.id === flashId ? 'row-flash' : '', r.state === 'pending' ? 'row-dim' : '']
              .filter(Boolean)
              .join(' ') || undefined
          }
          empty={
            <EmptyState icon={<IconGlobe size={26} />} title={t('china.emptyTitle')} description={t('china.emptyDesc')} />
          }
        />
      </Card>
      </>
      )}
    </div>
  );
}
