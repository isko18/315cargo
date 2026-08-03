import { useEffect, useState } from 'react';
import { ApiError, get, patch } from '../api';
import { IconTariff, IconWeight, IconRevenue } from '../components/Icons';
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
  price_per_kg_usd: string;
};

export default function TariffPage() {
  const { t } = useI18n();
  const [cargo, setCargo] = useState<MyCargo | null>(null);
  const [price, setPrice] = useState('');
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    get<MyCargo>('/api/manage/cargo/')
      .then((c) => {
        setCargo(c);
        setPrice(c.price_per_kg_usd);
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
      const updated = await patch<MyCargo>('/api/manage/cargo/', { price_per_kg_usd: price });
      setCargo(updated);
      setPrice(updated.price_per_kg_usd);
      setMsg(t('tariff.saved'));
    } catch (e) {
      setErr(formError(e));
    } finally {
      setBusy(false);
    }
  }

  const current = cargo ? parseFloat(cargo.price_per_kg_usd) : 0;
  const preview = priceNum * 3;

  return (
    <div>
      <PageHeader title={t('tariff.title')} subtitle={t('tariff.subtitle')} />

      <StatGrid className="mb-lg">
        <Stat icon={<IconRevenue size={19} />} tone="green" label={t('tariff.current')} value={`$${current.toFixed(2)}`} hint={t('tariff.perKg')} />
        <Stat icon={<IconWeight size={19} />} tone="blue" label={t('tariff.example3')} value={`$${preview.toFixed(2)}`} hint={t('tariff.byInput')} />
      </StatGrid>

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
                suffix="$ / кг"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                placeholder="0.00"
                autoFocus
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
