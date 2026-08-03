import { useEffect, useMemo, useState } from 'react';
import { ApiError, get, api } from '../api';
import { useI18n } from '../i18n';
import { IconCheck, IconPin } from '../components/Icons';
import { Alert, Button, Card, CardBody, CardHeader, Checkbox, Field, formError, Input, PageHeader } from '../ui';

type AddressForm = {
  phone: string;
  province: string;
  city: string;
  district: string;
  detail_address: string;
  postal_code: string;
  instructions: string;
  is_active: boolean;
};

const EMPTY: AddressForm = {
  phone: '',
  province: '',
  city: '',
  district: '',
  detail_address: '',
  postal_code: '',
  instructions: '',
  is_active: true,
};

// Демо-код клиента для предпросмотра «строки для вставки» (реальный код
// подставляется бэкендом каждому клиенту в приложении).
const SAMPLE_CODE = 'C1234567';

export default function DeliveryAddressPage() {
  const { t } = useI18n();
  const [form, setForm] = useState<AddressForm>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');

  useEffect(() => {
    get('/api/delivery-address/')
      .then((d: any) =>
        setForm({
          phone: d.phone ?? '',
          province: d.province ?? '',
          city: d.city ?? '',
          district: d.district ?? '',
          detail_address: d.detail_address ?? '',
          postal_code: d.postal_code ?? '',
          instructions: d.instructions ?? '',
          is_active: d.is_active ?? true,
        }),
      )
      .catch((e) => setErr((e as ApiError).message))
      .finally(() => setLoading(false));
  }, []);

  function set<K extends keyof AddressForm>(k: K, v: AddressForm[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  // Живой предпросмотр строки для 智能填写. 收货人 = только код клиента.
  const preview = useMemo(() => {
    const region = [form.province, form.city, form.district].map((s) => s.trim()).filter(Boolean).join('');
    return [SAMPLE_CODE, form.phone.trim(), region, form.detail_address.trim(), form.postal_code.trim()]
      .filter(Boolean)
      .join(' ');
  }, [form]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setErr('');
    setMsg('');
    setBusy(true);
    try {
      await api('/api/delivery-address/', {
        method: 'PUT',
        body: JSON.stringify({
          phone: form.phone.trim(),
          province: form.province.trim(),
          city: form.city.trim(),
          district: form.district.trim(),
          detail_address: form.detail_address.trim(),
          postal_code: form.postal_code.trim(),
          instructions: form.instructions.trim(),
          is_active: form.is_active,
        }),
      });
      setMsg(t('daddr.saved'));
    } catch (e) {
      setErr(formError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader title={t('daddr.title')} subtitle={t('daddr.subtitle')} />

      {msg && <Alert variant="success">{msg}</Alert>}

      <div className="grid-2" style={{ alignItems: 'start' }}>
        <Card>
          <CardHeader title={t('daddr.formCard')} description={t('daddr.formDesc')} />
          <CardBody>
            <form id="daddr-form" onSubmit={save}>
              <Alert variant="info">{t('daddr.recipientAuto')}</Alert>
              <Field label={t('daddr.phone')} className="mt-md">
                <Input value={form.phone} onChange={(e) => set('phone', e.target.value)} placeholder="+86 138 0000 0000" disabled={loading} />
              </Field>
              <div className="grid-2 mt-md">
                <Field label={t('daddr.province')}>
                  <Input value={form.province} onChange={(e) => set('province', e.target.value)} placeholder="广东省" disabled={loading} />
                </Field>
                <Field label={t('daddr.city')}>
                  <Input value={form.city} onChange={(e) => set('city', e.target.value)} placeholder="广州市" disabled={loading} />
                </Field>
                <Field label={t('daddr.district')}>
                  <Input value={form.district} onChange={(e) => set('district', e.target.value)} placeholder="白云区" disabled={loading} />
                </Field>
                <Field label={t('daddr.postal')}>
                  <Input value={form.postal_code} onChange={(e) => set('postal_code', e.target.value)} placeholder="510000" disabled={loading} />
                </Field>
              </div>
              <Field label={t('daddr.detail')} className="mt-md">
                <Input value={form.detail_address} onChange={(e) => set('detail_address', e.target.value)} placeholder="XX路 100号 315CARGO仓库" disabled={loading} />
              </Field>
              <Field label={t('daddr.instructions')} helper={t('daddr.instructionsHint')} className="mt-md">
                <textarea
                  value={form.instructions}
                  onChange={(e) => set('instructions', e.target.value)}
                  placeholder={t('daddr.instructionsPlaceholder')}
                  disabled={loading}
                />
              </Field>
              <div className="mt-md">
                <Checkbox checked={form.is_active} onChange={(v) => set('is_active', v)} disabled={loading}>
                  {t('daddr.isActive')}
                </Checkbox>
              </div>

              {err && <Alert variant="error" className="prewrap">{err}</Alert>}

              <div className="mt-md">
                <Button type="submit" form="daddr-form" loading={busy} disabled={loading} icon={<IconCheck size={18} />}>
                  {t('common.save')}
                </Button>
              </div>
            </form>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title={t('daddr.previewCard')} description={t('daddr.previewDesc')} />
          <CardBody>
            <div className="daddr-preview">
              <IconPin size={18} />
              <code>{preview || t('daddr.previewEmpty')}</code>
            </div>
            <p className="helper mt-md">
              {t('daddr.previewNote')} <span className="mono">{SAMPLE_CODE}</span>
            </p>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
