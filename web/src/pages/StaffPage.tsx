import { useEffect, useState } from 'react';
import { ApiError, get, getRole, patch, post } from '../api';
import { usePickup } from '../pickupContext';
import { DEFAULT_OPERATOR_TABS, GRANTABLE_TABS } from '../tabs';
import { useI18n } from '../i18n';
import { IconPlus, IconStaff } from '../components/Icons';
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

type Staff = {
  id: number;
  phone: string;
  full_name: string;
  cargo: number | null;
  cargo_title: string | null;
  pickup_point: number | null;
  pickup_point_title: string | null;
  is_cargo_admin: boolean;
  is_china_staff: boolean;
  is_active: boolean;
  allowed_tabs: string[];
};
type Cargo = { id: number; title: string };

export default function StaffPage() {
  const { t } = useI18n();
  const { points } = usePickup();
  const isSuper = Boolean(getRole().is_superuser);
  const [list, setList] = useState<Staff[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [cargos, setCargos] = useState<Cargo[]>([]);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);

  const [phone, setPhone] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [isAdmin, setIsAdmin] = useState(false);
  const [isChina, setIsChina] = useState(false);
  const [active, setActive] = useState(true);
  const [cargo, setCargo] = useState('');
  const [pickupPoint, setPickupPoint] = useState('');
  const [tabsSel, setTabsSel] = useState<Set<string>>(new Set(DEFAULT_OPERATOR_TABS));

  function toggleTab(tab: string) {
    setTabsSel((s) => {
      const n = new Set(s);
      n.has(tab) ? n.delete(tab) : n.add(tab);
      return n;
    });
  }

  async function reload() {
    setLoading(true);
    try {
      const d = await get('/api/manage/staff/');
      setList((d?.results ?? d) as Staff[]);
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
    // Список карго нужен только супер-владельцу (он назначает карго). Админ
    // карго создаёт сотрудников только в своём карго — выбор ему не нужен.
    if (isSuper) get<Cargo[]>('/api/cargo-companies/').then(setCargos).catch(() => {});
  }, [isSuper]);

  const passwordTooShort = password.length > 0 && password.length < 6;
  // Создание: телефон + пароль ≥6. Редактирование: пароль опционален.
  const canSubmit = editId
    ? !passwordTooShort
    : phone.trim().length > 0 && password.length >= 6;

  function resetForm() {
    setEditId(null);
    setPhone('');
    setFullName('');
    setPassword('');
    setIsAdmin(false);
    setIsChina(false);
    setActive(true);
    setCargo('');
    setPickupPoint('');
    setTabsSel(new Set(DEFAULT_OPERATOR_TABS));
    setErr('');
  }

  function openCreate() {
    resetForm();
    setMsg('');
    setOpen(true);
  }

  function openEdit(s: Staff) {
    setEditId(s.id);
    setPhone(s.phone);
    setFullName(s.full_name);
    setPassword('');
    setIsAdmin(s.is_cargo_admin);
    setIsChina(s.is_china_staff);
    setActive(s.is_active);
    setCargo(s.cargo ? String(s.cargo) : '');
    setPickupPoint(s.pickup_point ? String(s.pickup_point) : '');
    setTabsSel(new Set(s.allowed_tabs ?? []));
    setErr('');
    setMsg('');
    setOpen(true);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setErr('');
    setMsg('');
    setBusy(true);
    try {
      const allowed = isAdmin || isChina ? [] : [...tabsSel];
      if (editId) {
        const body: Record<string, unknown> = {
          full_name: fullName.trim(),
          is_cargo_admin: isAdmin,
          is_china_staff: isChina,
          is_active: active,
          allowed_tabs: allowed,
          pickup_point: pickupPoint ? Number(pickupPoint) : null,
        };
        if (password) body.password = password;
        await patch(`/api/manage/staff/${editId}/`, body);
        setMsg(t('staff.savedMsg'));
      } else {
        const body: Record<string, unknown> = {
          phone: phone.trim(),
          full_name: fullName.trim(),
          password,
          is_cargo_admin: isAdmin,
          is_china_staff: isChina,
          allowed_tabs: allowed,
        };
        if (cargo) body.cargo = Number(cargo);
        if (pickupPoint) body.pickup_point = Number(pickupPoint);
        const created = await post<Staff>('/api/manage/staff/', body);
        setMsg(`${t('staff.createdPrefix')} ${created.phone}`);
      }
      setOpen(false);
      resetForm();
      await reload();
    } catch (e) {
      setErr(formError(e));
    } finally {
      setBusy(false);
    }
  }

  async function toggleActive(s: Staff) {
    try {
      await patch(`/api/manage/staff/${s.id}/`, { is_active: !s.is_active });
      await reload();
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  const activeCount = (list ?? []).filter((s) => s.is_active).length;

  const columns: Column<Staff>[] = [
    {
      key: 'staff',
      header: t('staff.colStaff'),
      sortValue: (s) => s.full_name || s.phone,
      render: (s) => (
        <div>
          <div className="strong">{s.full_name || '—'}</div>
          <div className="muted mono" style={{ fontSize: 12.5 }}>{s.phone}</div>
        </div>
      ),
    },
    { key: 'cargo', header: t('common.cargo'), render: (s) => s.cargo_title || '—' },
    { key: 'pickup', header: t('wh.pvz'), render: (s) => <span style={{ fontSize: 13 }}>{s.pickup_point_title || '—'}</span> },
    {
      key: 'role',
      header: t('staff.colRole'),
      render: (s) =>
        s.is_cargo_admin ? (
          <Badge variant="violet">{t('staff.badgeAdmin')}</Badge>
        ) : s.is_china_staff ? (
          <Badge variant="amber">{t('staff.badgeChina')}</Badge>
        ) : (
          <div className="cluster gap-sm" style={{ rowGap: 4 }}>
            <Badge variant="gray">{t('staff.badgeOperator')}</Badge>
            {(s.allowed_tabs ?? []).length > 0 ? (
              (s.allowed_tabs ?? []).map((tab) => (
                <span key={tab} className="tab-chip">
                  {t(`nav.${tab}`)}
                </span>
              ))
            ) : (
              <span className="muted" style={{ fontSize: 12 }}>{t('staff.noTabs')}</span>
            )}
          </div>
        ),
    },
    {
      key: 'status',
      header: t('common.status'),
      sortValue: (s) => (s.is_active ? 0 : 1),
      render: (s) => (
        <Badge variant={s.is_active ? 'ok' : 'warn'} dot>
          {s.is_active ? t('common.active') : t('common.inactive')}
        </Badge>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      render: (s) => (
        <div className="cluster gap-sm" style={{ justifyContent: 'flex-end', flexWrap: 'nowrap' }}>
          <Button variant="subtle" size="sm" onClick={() => openEdit(s)}>
            {t('common.edit')}
          </Button>
          <Button variant="subtle" size="sm" onClick={() => toggleActive(s)}>
            {s.is_active ? t('common.off') : t('common.on')}
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader title={t('staff.title')} subtitle={t('staff.subtitle')} />

      {msg && <Alert variant="success">{msg}</Alert>}

      <Card>
        <CardHeader
          title={t('staff.list')}
          actions={
            <div className="cluster gap-sm">
              <Badge variant="plain">{list?.length ?? 0} {t('staff.all')}</Badge>
              <Badge variant="ok">{activeCount} {t('staff.activeCnt')}</Badge>
              <Button size="sm" onClick={openCreate} icon={<IconPlus size={16} />}>
                {t('common.create')}
              </Button>
            </div>
          }
        />
        <DataTable
          columns={columns.filter((c) => isSuper || c.key !== 'cargo')}
          rows={list}
          loading={loading}
          getRowKey={(s) => s.id}
          rowClassName={(s) => (s.is_active ? undefined : 'row-dim')}
          empty={
            <EmptyState
              icon={<IconStaff size={26} />}
              title={t('staff.emptyTitle')}
              description={t('staff.emptyDesc')}
              action={
                <Button size="sm" onClick={openCreate} icon={<IconPlus size={16} />}>
                  {t('common.create')}
                </Button>
              }
            />
          }
        />
      </Card>

      {open && (
        <Modal
          title={editId ? t('staff.edit') : t('staff.new')}
          description={editId ? phone : t('staff.newDesc')}
          onClose={() => setOpen(false)}
          footer={
            <>
              <Button variant="subtle" onClick={() => setOpen(false)}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" form="staff-form" loading={busy} disabled={!canSubmit} icon={<IconPlus size={18} />}>
                {editId ? t('common.save') : t('common.create')}
              </Button>
            </>
          }
        >
          <form id="staff-form" onSubmit={submit}>
            <div className="grid-2">
              <Field label={t('staff.phone')} required={!editId}>
                <Input
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="+996700000000"
                  inputMode="tel"
                  disabled={Boolean(editId)}
                />
              </Field>
              <Field label={t('staff.fullName')}>
                <Input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Имя Фамилия" />
              </Field>
            </div>

            <Field
              label={editId ? t('staff.newPassword') : t('staff.password')}
              required={!editId}
              className="mt-md"
              error={passwordTooShort ? t('staff.pwdMinErr') : undefined}
              helper={passwordTooShort ? undefined : editId ? t('staff.pwdKeep') : t('staff.pwdMin')}
            >
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••"
                autoComplete="new-password"
                invalid={passwordTooShort}
              />
            </Field>

            <div className={`mt-md ${isSuper && !editId ? 'grid-2' : ''}`}>
              {/* Выбор карго — только у супер-владельца; админу карго ставится своё. */}
              {isSuper && !editId && (
                <Field label={t('common.cargo')} helper={t('staff.cargoHelper')}>
                  <Select value={cargo} onChange={(e) => setCargo(e.target.value)}>
                    <option value="">{t('staff.cargoMine')}</option>
                    {cargos.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.title}
                      </option>
                    ))}
                  </Select>
                </Field>
              )}
              <Field label={t('staff.pickup')}>
                <Select value={pickupPoint} onChange={(e) => setPickupPoint(e.target.value)}>
                  <option value="">{t('staff.pickupNone')}</option>
                  {points.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.title}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>

            <div className="stack gap-sm mt-md">
              <Checkbox
                checked={isAdmin}
                onChange={(v) => {
                  setIsAdmin(v);
                  if (v) setIsChina(false);
                }}
              >
                {t('staff.roleAdmin')}
              </Checkbox>
              {isSuper && (
                <Checkbox
                  checked={isChina}
                  onChange={(v) => {
                    setIsChina(v);
                    if (v) setIsAdmin(false);
                  }}
                >
                  {t('staff.roleChina')}
                </Checkbox>
              )}
              {editId && (
                <Checkbox checked={active} onChange={setActive}>
                  {t('staff.activeField')}
                </Checkbox>
              )}
            </div>

            {isAdmin ? (
              <Alert variant="info" className="mt-md">
                {t('staff.adminAllTabs')}
              </Alert>
            ) : isChina ? (
              <Alert variant="info" className="mt-md">
                {t('staff.chinaOnly')}
              </Alert>
            ) : (
              <Field label={t('staff.tabsLabel')} className="mt-md" helper={t('staff.tabsHelper')}>
                <div className="tab-grid">
                  {GRANTABLE_TABS.map((tab) => (
                    <Checkbox key={tab} checked={tabsSel.has(tab)} onChange={() => toggleTab(tab)}>
                      {t(`nav.${tab}`)}
                    </Checkbox>
                  ))}
                </div>
              </Field>
            )}

            {err && <Alert variant="error">{err}</Alert>}
          </form>
        </Modal>
      )}
    </div>
  );
}
