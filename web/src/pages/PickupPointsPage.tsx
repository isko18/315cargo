import { useState } from 'react';
import { ApiError, patch, post } from '../api';
import { usePickup, type PickupPoint } from '../pickupContext';
import { useI18n } from '../i18n';
import { IconCheck, IconPlus, IconWarehouse } from '../components/Icons';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  Column,
  DataTable,
  EmptyState,
  Field,
  formError,
  Input,
  Modal,
  PageHeader,
} from '../ui';

const EMPTY = { title: '', address: '', phone: '', work_schedule: '' };

export default function PickupPointsPage() {
  const { t } = useI18n();
  const { points, reload, activeId, setActiveId } = usePickup();
  const [form, setForm] = useState({ ...EMPTY });
  const [editId, setEditId] = useState<number | null>(null);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  function set<K extends keyof typeof form>(k: K, v: string) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  function openCreate() {
    setEditId(null);
    setForm({ ...EMPTY });
    setErr('');
    setMsg('');
    setOpen(true);
  }

  function startEdit(p: PickupPoint) {
    setEditId(p.id);
    setForm({ title: p.title, address: p.address, phone: p.phone, work_schedule: p.work_schedule });
    setMsg('');
    setErr('');
    setOpen(true);
  }

  function cancel() {
    setOpen(false);
    setEditId(null);
    setForm({ ...EMPTY });
  }

  const canSubmit = form.title.trim().length > 0 && form.address.trim().length > 0;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setErr('');
    setMsg('');
    setBusy(true);
    try {
      if (editId) {
        await patch(`/api/manage/pickup-points/${editId}/`, form);
        setMsg(t('pickup.updated'));
      } else {
        await post('/api/manage/pickup-points/', form);
        setMsg(t('pickup.created'));
      }
      setOpen(false);
      setEditId(null);
      setForm({ ...EMPTY });
      reload();
    } catch (e) {
      setErr(formError(e));
    } finally {
      setBusy(false);
    }
  }

  async function toggle(p: PickupPoint) {
    try {
      await patch(`/api/manage/pickup-points/${p.id}/`, { is_active: !p.is_active });
      reload();
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  const activeCount = points.filter((p) => p.is_active).length;

  const columns: Column<PickupPoint>[] = [
    {
      key: 'title',
      header: t('pickup.name'),
      sortValue: (p) => p.title,
      render: (p) => (
        <div className="cluster gap-sm">
          <span className="strong">{p.title}</span>
          {activeId === p.id && <Badge variant="blue">{t('pickup.activeBadge')}</Badge>}
        </div>
      ),
    },
    { key: 'address', header: t('pickup.address'), render: (p) => <span style={{ fontSize: 13 }}>{p.address || '—'}</span> },
    { key: 'phone', header: t('pickup.phone'), render: (p) => <span className="mono" style={{ fontSize: 13 }}>{p.phone || '—'}</span> },
    { key: 'schedule', header: t('pickup.scheduleCol'), render: (p) => <span style={{ fontSize: 13 }}>{p.work_schedule || '—'}</span> },
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
    {
      key: 'actions',
      header: '',
      align: 'right',
      render: (p) => (
        <div className="cluster gap-sm nowrap" style={{ justifyContent: 'flex-end', flexWrap: 'nowrap' }}>
          <Button variant="subtle" size="sm" onClick={() => setActiveId(p.id)} disabled={activeId === p.id}>
            {t('pickup.select')}
          </Button>
          <Button variant="subtle" size="sm" onClick={() => startEdit(p)}>
            {t('common.edit')}
          </Button>
          <Button variant="subtle" size="sm" onClick={() => toggle(p)}>
            {p.is_active ? t('common.off') : t('common.on')}
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader title={t('pickup.title')} subtitle={t('pickup.subtitle')} />

      {msg && <Alert variant="success">{msg}</Alert>}

      <Card>
        <CardHeader
          title={t('pickup.list')}
          actions={
            <div className="cluster gap-sm">
              <Badge variant="plain">{points.length} {t('pickup.all')}</Badge>
              <Badge variant="ok">{activeCount} {t('pickup.activeCnt')}</Badge>
              <Button size="sm" onClick={openCreate} icon={<IconPlus size={16} />}>
                {t('pickup.new')}
              </Button>
            </div>
          }
        />
        <DataTable
          columns={columns}
          rows={points}
          getRowKey={(p) => p.id}
          rowClassName={(p) => (p.is_active ? undefined : 'row-dim')}
          empty={
            <EmptyState
              icon={<IconWarehouse size={26} />}
              title={t('pickup.emptyTitle')}
              description={t('pickup.emptyDesc')}
              action={
                <Button size="sm" onClick={openCreate} icon={<IconPlus size={16} />}>
                  {t('pickup.new')}
                </Button>
              }
            />
          }
        />
      </Card>

      {open && (
        <Modal
          title={editId ? t('pickup.edit') : t('pickup.new')}
          description={editId ? `#${editId}` : t('pickup.subNew')}
          onClose={cancel}
          footer={
            <>
              <Button variant="subtle" onClick={cancel}>
                {t('common.cancel')}
              </Button>
              <Button
                type="submit"
                form="pvz-form"
                loading={busy}
                disabled={!canSubmit}
                icon={editId ? <IconCheck size={18} /> : <IconPlus size={18} />}
              >
                {editId ? t('common.save') : t('pickup.create')}
              </Button>
            </>
          }
        >
          <form id="pvz-form" onSubmit={submit}>
            <div className="grid-2">
              <Field label={t('pickup.name')} required>
                <Input value={form.title} onChange={(e) => set('title', e.target.value)} placeholder="ПВЗ Бишкек Центр" autoFocus />
              </Field>
              <Field label={t('pickup.phone')}>
                <Input value={form.phone} onChange={(e) => set('phone', e.target.value)} placeholder="+996700100100" inputMode="tel" />
              </Field>
            </div>
            <Field label={t('pickup.address')} required className="mt-md">
              <Input value={form.address} onChange={(e) => set('address', e.target.value)} placeholder="Бишкек, ул. Чуй 100" />
            </Field>
            <Field label={t('pickup.schedule')} className="mt-md">
              <Input value={form.work_schedule} onChange={(e) => set('work_schedule', e.target.value)} placeholder="Пн-Сб 09:00-19:00" />
            </Field>
            {err && <Alert variant="error">{err}</Alert>}
          </form>
        </Modal>
      )}
    </div>
  );
}
