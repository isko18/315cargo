import { useEffect, useMemo, useState } from 'react';
import { money } from '../money';
import { ApiError, get, patch } from '../api';
import { IconTariff, IconWeight, IconRevenue, IconStaff, IconCheck } from '../components/Icons';
import { useI18n } from '../i18n';
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardHeader,
  Field,
  formError,
  Input,
  PageHeader,
  Stat,
  StatGrid,
} from '../ui';

type MyCargo = {
  id: number;
  title: string;
  price_per_kg_kgs: string;
  client_code_prefix: string;
  client_code_seq: number;
  client_code_next: string;
};

// Ширина номера в клиентском коде — зеркалит CLIENT_CODE_DIGITS на бэкенде.
const CODE_DIGITS = 4;
const PREFIX_RE = /^[A-Za-zА-Яа-яЁё0-9]{1,6}$/;

const pad = (n: number) => String(n).padStart(CODE_DIGITS, '0');

export default function CargoSettingsPage() {
  const { t } = useI18n();
  const [cargo, setCargo] = useState<MyCargo | null>(null);
  const [price, setPrice] = useState('');
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);

  // Формат клиентского кода.
  const [prefix, setPrefix] = useState('');
  const [codeErr, setCodeErr] = useState('');
  const [codeMsg, setCodeMsg] = useState('');
  const [codeBusy, setCodeBusy] = useState(false);

  useEffect(() => {
    get<MyCargo>('/api/manage/cargo/')
      .then((c) => {
        setCargo(c);
        setPrice(c.price_per_kg_kgs);
        setPrefix(c.client_code_prefix);
      })
      .catch((e) => setErr((e as ApiError).message));
  }, []);

  const priceNum = parseFloat(price || '0') || 0;
  const invalid = price !== '' && priceNum < 0;
  const canSave = price !== '' && !invalid;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!canSave) return;
    setErr('');
    setMsg('');
    setBusy(true);
    try {
      const updated = await patch<MyCargo>('/api/manage/cargo/', { price_per_kg_kgs: price });
      setCargo(updated);
      setPrice(updated.price_per_kg_kgs);
      setMsg(t('tariff.saved'));
    } catch (e) {
      setErr(formError(e));
    } finally {
      setBusy(false);
    }
  }

  // Предпросмотр: какие коды получат следующие клиенты при текущем префиксе.
  const trimmed = prefix.trim();
  const prefixBad = trimmed.length > 0 && !PREFIX_RE.test(trimmed);
  const nextNum = (cargo?.client_code_seq ?? 0) + 1;
  const samples = useMemo(
    () => [0, 1, 2].map((i) => `${trimmed || '?'}${pad(nextNum + i)}`),
    [trimmed, nextNum],
  );
  const prefixDirty = Boolean(cargo) && trimmed !== cargo!.client_code_prefix;
  const canSavePrefix = trimmed.length > 0 && !prefixBad && prefixDirty;

  async function savePrefix(e: React.FormEvent) {
    e.preventDefault();
    if (!canSavePrefix) return;
    setCodeErr('');
    setCodeMsg('');
    setCodeBusy(true);
    try {
      const updated = await patch<MyCargo>('/api/manage/cargo/', { client_code_prefix: trimmed });
      setCargo(updated);
      setPrefix(updated.client_code_prefix);
      setCodeMsg(t('ccode.saved'));
    } catch (e) {
      setCodeErr(formError(e));
    } finally {
      setCodeBusy(false);
    }
  }

  const current = cargo ? parseFloat(cargo.price_per_kg_kgs) : 0;
  const preview = priceNum * 3;

  return (
    <div>
      <PageHeader title={t('cset.title')} subtitle={t('cset.subtitle')} />

      <StatGrid className="mb-lg">
        <Stat icon={<IconRevenue size={19} />} tone="green" label={t('tariff.current')} value={money(current)} hint={t('tariff.perKg')} />
        <Stat icon={<IconWeight size={19} />} tone="blue" label={t('tariff.example3')} value={money(preview)} hint={t('tariff.byInput')} />
        <Stat
          icon={<IconStaff size={19} />}
          tone="violet"
          label={t('ccode.nextStat')}
          value={cargo ? cargo.client_code_next : '—'}
          hint={`${t('ccode.issued')}: ${cargo?.client_code_seq ?? 0}`}
        />
      </StatGrid>

      <Card>
        <CardHeader title={t('ccode.card')} description={t('ccode.cardDesc')} />
        <CardBody>
          <form onSubmit={savePrefix}>
            <div className="row" style={{ alignItems: 'flex-start' }}>
              <Field
                label={t('ccode.prefixLabel')}
                helper={!prefixBad ? t('ccode.prefixHelper') : undefined}
                error={prefixBad ? t('ccode.prefixErr') : undefined}
                style={{ maxWidth: 200 }}
              >
                <Input
                  value={prefix}
                  onChange={(e) => setPrefix(e.target.value)}
                  placeholder="X"
                  autoComplete="off"
                  invalid={prefixBad}
                  style={{ fontSize: 18, fontWeight: 600 }}
                />
              </Field>

              <Field label={t('ccode.previewLabel')} helper={t('ccode.previewHelper')} style={{ flex: 1 }}>
                <div className="ccode-preview">
                  {samples.map((code, i) => (
                    <span key={code} className={`ccode-chip${i === 0 ? ' is-next' : ''}`}>
                      {code}
                    </span>
                  ))}
                </div>
              </Field>
            </div>

            <Alert variant="info">{t('ccode.note')}</Alert>

            <Button type="submit" loading={codeBusy} disabled={!canSavePrefix} className="mt-md" icon={<IconCheck size={18} />}>
              {t('ccode.save')}
            </Button>

            {codeErr && <Alert variant="error" className="prewrap">{codeErr}</Alert>}
            {codeMsg && <Alert variant="success">{codeMsg}</Alert>}
          </form>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title={cargo ? cargo.title : t('tariff.myCargo')} description={t('tariff.editCard')} />
        <CardBody>
          <form onSubmit={save}>
            <Field
              label={t('tariff.priceLabel')}
              helper={t('tariff.priceHelper')}
              error={invalid ? t('tariff.negative') : undefined}
              style={{ maxWidth: 260 }}
            >
              <Input
                type="number"
                min="0"
                step="0.01"
                inputMode="decimal"
                suffix="сом / кг"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                placeholder="0.00"
                invalid={invalid}
                style={{ fontSize: 18, fontWeight: 600 }}
              />
            </Field>

            <Button type="submit" loading={busy} disabled={!canSave} className="mt-md" icon={<IconTariff size={18} />}>
              {t('tariff.save')}
            </Button>

            {err && <Alert variant="error">{err}</Alert>}
            {msg && <Alert variant="success">{msg}</Alert>}
          </form>
        </CardBody>
      </Card>
    </div>
  );
}
