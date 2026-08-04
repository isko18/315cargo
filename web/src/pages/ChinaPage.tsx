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

export default function ChinaPage() {
  const { t } = useI18n();
  const [tab, setTab] = useState<'china' | 'history'>('china');
  const [track, setTrack] = useState('');
  const [clientCode, setClientCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [log, setLog] = useState<Entry[]>([]);
  const [flashId, setFlashId] = useState<number | null>(null);
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
      const body: Record<string, unknown> = { track_number: tn, status: CHINA_STATUS };
      if (clientCode.trim()) body.client_code = clientCode.trim();
      const r = await post<Entry>('/api/parcels/scan/', body);
      setLog((l) => [r, ...l]);
      setTrack('');
      setFlashId(r.parcel.id);
      window.setTimeout(() => setFlashId((cur) => (cur === r.parcel.id ? null : cur)), 1400);
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  }

  // Глобальный перехват штрих-сканера — код подхватывается без клика в поле.
  useBarcodeScanner((code) => {
    setTrack(code);
    scan(code);
  });

  // Сводка сессии по типу приёмки.
  const counts = {
    order: log.filter((e) => e.result === 'created_from_order').length,
    manual: log.filter((e) => e.result === 'created_manual').length,
    unclaimed: log.filter((e) => e.result === 'created_pending').length,
  };

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
      key: 'client',
      header: t('common.client'),
      render: (e) =>
        e.parcel.user ? (
          <Badge variant="ok" className="mono">{e.parcel.client_code}</Badge>
        ) : (
          <Badge variant="warn">{t('common.noClient')}</Badge>
        ),
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
        <OperationHistory type="china" reloadSignal={log.length} />
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
            <Button onClick={() => scan()} loading={busy} disabled={!track.trim()} icon={<IconCheck size={18} />}>
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
              <Badge variant="plain">{log.length} {t('common.pcs')}</Badge>
              {counts.order > 0 && <Badge variant="green">{counts.order} {t('china.chipOrder')}</Badge>}
              {counts.manual > 0 && <Badge variant="teal">{counts.manual} {t('china.chipManual')}</Badge>}
              {counts.unclaimed > 0 && <Badge variant="amber">{counts.unclaimed} {t('china.chipUnclaimed')}</Badge>}
              {log.length > 0 && (
                <Button variant="subtle" size="sm" onClick={() => { setLog([]); setFlashId(null); }}>
                  {t('china.clear')}
                </Button>
              )}
            </div>
          }
        />
        <DataTable
          columns={columns}
          rows={log}
          getRowKey={(e) => e.parcel.id}
          rowClassName={(e) => (e.parcel.id === flashId ? 'row-flash' : undefined)}
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
