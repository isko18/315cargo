import { useEffect, useState } from 'react';
import { ApiError, get, patch, post } from '../api';
import { usePickup } from '../pickupContext';
import { useI18n } from '../i18n';
import { IconCheck, IconPlus, IconRevenue } from '../components/Icons';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  Checkbox,
  Column,
  DataTable,
  EmptyState,
  Field,
  formError,
  Input,
  Modal,
  PageHeader,
  Select,
} from '../ui';

type Tariff = {
  id: number;
  title: string;
  base_price: string;
  price_per_kg: string;
  free_weight_kg: string;
  min_price: string | null;
  is_default: boolean;
  is_active: boolean;
  pickup_point: number | null;
};

const EMPTY = {
  title: '',
  base_price: '',
  price_per_kg: '0',
  free_weight_kg: '0',
  min_price: '',
  is_default: false,
  is_active: true,
  pickup_point: '',
};

export default function DeliveryTariffPage() {
  const { t } = useI18n();
  const { points } = usePickup();
  const [list, setList] = useState<Tariff[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState({ ...EMPTY });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');

  function reload() {
    setLoading(true);
    get('/api/manage/city-delivery-tariffs/')
      .then((d: any) => setList((d?.results ?? d) as Tariff[]))
      .catch((e) => setErr((e as ApiError).message))
      .finally(() => setLoading(false));
  }
  useEffect(() => {
    reload();
  }, []);

  function set<K extends keyof typeof form>(k: K, v: string | boolean) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  function openCreate() {
    setEditId(null);
    setForm({ ...EMPTY });
    setErr('');
    setMsg('');
    setOpen(true);
  }
  function openEdit(x: Tariff) {
    setEditId(x.id);
    setForm({
      title: x.title,
      base_price: x.base_price,
      price_per_kg: x.price_per_kg,
      free_weight_kg: x.free_weight_kg,
      min_price: x.min_price ?? '',
      is_default: x.is_default,
      is_active: x.is_active,
      pickup_point: x.pickup_point ? String(x.pickup_point) : '',
    });
    setErr('');
    setMsg('');
    setOpen(true);
  }

  const canSubmit = form.title.trim() && form.base_price.trim();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setErr('');
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        title: form.title.trim(),
        base_price: form.base_price.trim(),
        price_per_kg: form.price_per_kg.trim() || '0',
        free_weight_kg: form.free_weight_kg.trim() || '0',
        min_price: form.min_price.trim() || null,
        is_default: form.is_default,
        is_active: form.is_active,
        pickup_point: form.pickup_point ? Number(form.pickup_point) : null,
      };
      if (editId) await patch(`/api/manage/city-delivery-tariffs/${editId}/`, body);
      else await post('/api/manage/city-delivery-tariffs/', body);
      setMsg(editId ? t('dtariff.saved') : t('dtariff.created'));
      setOpen(false);
      reload();
    } catch (e) {
      setErr(formError(e));
    } finally {
      setBusy(false);
    }
  }

  async function toggle(x: Tariff) {
    try {
      await patch(`/api/manage/city-delivery-tariffs/${x.id}/`, { is_active: !x.is_active });
      reload();
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  const columns: Column<Tariff>[] = [
    {
      key: 'title',
      header: t('dtariff.name'),
      sortValue: (x) => x.title,
      render: (x) => (
        <div className="cluster gap-sm">
          <span className="strong">{x.title}</span>
          {x.is_default && <Badge variant="blue">{t('dtariff.default')}</Badge>}
        </div>
      ),
    },
    { key: 'base', header: t('dtariff.base'), align: 'right', render: (x) => <span className="num">{x.base_price}</span> },
    { key: 'perkg', header: t('dtariff.perKg'), align: 'right', render: (x) => <span className="num">{x.price_per_kg}</span> },
    { key: 'free', header: t('dtariff.free'), align: 'right', render: (x) => <span className="num">{x.free_weight_kg}</span> },
    { key: 'min', header: t('dtariff.min'), align: 'right', render: (x) => <span className="num">{x.min_price ?? '—'}</span> },
    {
      key: 'pickup',
      header: t('wh.pvz'),
      render: (x) => <span style={{ fontSize: 13 }}>{points.find((p) => p.id === x.pickup_point)?.title ?? '—'}</span>,
    },
    {
      key: 'status',
      header: t('common.status'),
      sortValue: (x) => (x.is_active ? 0 : 1),
      render: (x) => (
        <Badge variant={x.is_active ? 'ok' : 'warn'} dot>{x.is_active ? t('common.active') : t('common.inactive')}</Badge>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      render: (x) => (
        <div className="cluster gap-sm" style={{ justifyContent: 'flex-end', flexWrap: 'nowrap' }}>
          <Button variant="subtle" size="sm" onClick={() => openEdit(x)}>{t('common.edit')}</Button>
          <Button variant="subtle" size="sm" onClick={() => toggle(x)}>{x.is_active ? t('common.off') : t('common.on')}</Button>
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader title={t('dtariff.title')} subtitle={t('dtariff.subtitle')} />

      {msg && <Alert variant="success">{msg}</Alert>}

      <Card>
        <CardHeader
          title={t('dtariff.list')}
          actions={
            <Button size="sm" onClick={openCreate} icon={<IconPlus size={16} />}>{t('dtariff.new')}</Button>
          }
        />
        <DataTable
          columns={columns}
          rows={list}
          loading={loading}
          getRowKey={(x) => x.id}
          rowClassName={(x) => (x.is_active ? undefined : 'row-dim')}
          empty={
            <EmptyState
              icon={<IconRevenue size={26} />}
              title={t('dtariff.empty')}
              action={<Button size="sm" onClick={openCreate} icon={<IconPlus size={16} />}>{t('dtariff.new')}</Button>}
            />
          }
        />
      </Card>

      {open && (
        <Modal
          title={editId ? t('dtariff.edit') : t('dtariff.new')}
          onClose={() => setOpen(false)}
          footer={
            <>
              <Button variant="subtle" onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
              <Button type="submit" form="dtariff-form" loading={busy} disabled={!canSubmit} icon={editId ? <IconCheck size={18} /> : <IconPlus size={18} />}>
                {editId ? t('common.save') : t('common.create')}
              </Button>
            </>
          }
        >
          <form id="dtariff-form" onSubmit={submit}>
            <Field label={t('dtariff.name')} required>
              <Input value={form.title} onChange={(e) => set('title', e.target.value)} placeholder="Бишкек стандарт" autoFocus />
            </Field>
            <div className="grid-2 mt-md">
              <Field label={t('dtariff.base')} required helper={t('dtariff.currency')}>
                <Input type="number" min="0" step="0.01" inputMode="decimal" value={form.base_price} onChange={(e) => set('base_price', e.target.value)} placeholder="150" />
              </Field>
              <Field label={t('dtariff.perKg')}>
                <Input type="number" min="0" step="0.01" inputMode="decimal" value={form.price_per_kg} onChange={(e) => set('price_per_kg', e.target.value)} placeholder="30" />
              </Field>
              <Field label={t('dtariff.free')} helper={t('dtariff.freeHint')}>
                <Input type="number" min="0" step="0.001" inputMode="decimal" value={form.free_weight_kg} onChange={(e) => set('free_weight_kg', e.target.value)} placeholder="1" />
              </Field>
              <Field label={t('dtariff.min')}>
                <Input type="number" min="0" step="0.01" inputMode="decimal" value={form.min_price} onChange={(e) => set('min_price', e.target.value)} placeholder="—" />
              </Field>
            </div>
            <Field label={t('dtariff.pickup')} helper={t('dtariff.pickupHint')} className="mt-md" style={{ maxWidth: 300 }}>
              <Select value={form.pickup_point} onChange={(e) => set('pickup_point', e.target.value)}>
                <option value="">{t('dtariff.allPickups')}</option>
                {points.map((p) => (
                  <option key={p.id} value={p.id}>{p.title}</option>
                ))}
              </Select>
            </Field>
            <div className="stack gap-sm mt-md">
              <Checkbox checked={form.is_default} onChange={(v) => set('is_default', v)}>{t('dtariff.isDefault')}</Checkbox>
              <Checkbox checked={form.is_active} onChange={(v) => set('is_active', v)}>{t('dtariff.isActive')}</Checkbox>
            </div>
            {err && <Alert variant="error">{err}</Alert>}
          </form>
        </Modal>
      )}
    </div>
  );
}
