import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiError, get, patch, post } from '../api';
import { IconOverview, IconBox, IconStaff, IconTruck, IconAlert, IconPlus, IconCheck } from '../components/Icons';
import { useI18n } from '../i18n';
import InviteLink from '../components/InviteLink';
import type { Tone } from '../status';
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
  Skeleton,
  Stat,
  StatGrid,
} from '../ui';

type Totals = {
  cargo_count: number;
  active_cargo_count: number;
  user_count: number;
  parcel_count: number;
  order_count: number;
  pickup_point_count: number;
};
type CargoRow = {
  id: number;
  title: string;
  slug: string;
  code: string | null;
  is_active: boolean;
  users_count: number;
  parcels_count: number;
  orders_count: number;
  pickup_points_count: number;
};
type Overview = { totals: Totals; per_cargo: CargoRow[] };
type AdminInfo = { id: number; full_name: string; phone: string; is_active: boolean };

const EMPTY = {
  title: '',
  slug: '',
  code: '',
  client_code_prefix: '',
  phone: '',
  address: '',
  price_per_kg_kgs: '',
  is_active: true,
  owner_name: '',
  owner_phone: '',
  owner_password: '',
};

// Транслитерация кириллицы → латиница, чтобы slug получался и из русских
// названий («315CARGO Ош» → «315cargo-osh»).
const TRANSLIT: Record<string, string> = {
  а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh', з: 'z', и: 'i',
  й: 'y', к: 'k', л: 'l', м: 'm', н: 'n', о: 'o', п: 'p', р: 'r', с: 's', т: 't',
  у: 'u', ф: 'f', х: 'h', ц: 'ts', ч: 'ch', ш: 'sh', щ: 'sch', ъ: '', ы: 'y', ь: '',
  э: 'e', ю: 'yu', я: 'ya',
};

function autoSlug(s: string) {
  const latin = s
    .toLowerCase()
    .split('')
    .map((c) => (c in TRANSLIT ? TRANSLIT[c] : c))
    .join('');
  return latin.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}

export default function OverviewPage() {
  const { t } = useI18n();
  const nav = useNavigate();
  const [data, setData] = useState<Overview | null>(null);
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);

  const [open, setOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState({ ...EMPTY });
  const [busy, setBusy] = useState(false);
  const [modalErr, setModalErr] = useState('');
  const [banner, setBanner] = useState('');

  // Ссылка-приглашение редактируемого карго (приходит с бэкенда вместе с QR).
  const [invite, setInvite] = useState<{ url: string; qr: string } | null>(null);
  // Сброс пароля владельца (в режиме редактирования).
  const [admins, setAdmins] = useState<AdminInfo[]>([]);
  const [ownerId, setOwnerId] = useState('');
  const [newPwd, setNewPwd] = useState('');
  const [pwdBusy, setPwdBusy] = useState(false);
  const [pwdMsg, setPwdMsg] = useState('');
  const [pwdErr, setPwdErr] = useState('');

  function reload() {
    setLoading(true);
    get<Overview>('/api/admin/overview/')
      .then((d) => {
        setData(d);
        setForbidden(false);
      })
      .catch((e: ApiError) => {
        if (e.status === 403) setForbidden(true);
        else setErr(e.message);
      })
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
    setModalErr('');
    setBanner('');
    setInvite(null);
    setOpen(true);
  }

  async function openEdit(row: CargoRow) {
    setEditId(row.id);
    setModalErr('');
    setBanner('');
    setInvite(null);
    setAdmins([]);
    setOwnerId('');
    setNewPwd('');
    setPwdMsg('');
    setPwdErr('');
    setOpen(true);
    try {
      const [c, adm] = await Promise.all([
        get<any>(`/api/admin/cargos/${row.id}/`),
        get<AdminInfo[]>(`/api/admin/cargos/${row.id}/admins/`),
      ]);
      setForm({
        ...EMPTY,
        title: c.title ?? '',
        slug: c.slug ?? '',
        code: c.code ?? '',
        client_code_prefix: c.client_code_prefix ?? '',
        phone: c.phone ?? '',
        address: c.address ?? '',
        price_per_kg_kgs: String(c.price_per_kg_kgs ?? ''),
        is_active: Boolean(c.is_active),
      });
      setInvite(c.invite_url ? { url: c.invite_url, qr: c.invite_qr } : null);
      setAdmins(adm);
      if (adm.length) setOwnerId(String(adm[0].id));
    } catch (e) {
      setModalErr(formError(e));
    }
  }

  const pwdShort = form.owner_password.length > 0 && form.owner_password.length < 6;
  // Код карго необязателен, но если задан — только латиница/цифры/«-»/«_», 2–32.
  const codeBad = form.code.trim().length > 0 && !/^[A-Za-z0-9_-]{2,32}$/.test(form.code.trim());
  // Префикс клиентского кода: буквы/цифры, 1–6. Пусто — бэкенд подберёт сам.
  const prefixRaw = form.client_code_prefix.trim();
  const prefixBad = prefixRaw.length > 0 && !/^[A-Za-zА-Яа-яЁё0-9]{1,6}$/.test(prefixRaw);
  const prefixPreview = !prefixBad && prefixRaw ? `${prefixRaw}0001` : undefined;
  const cargoValid = Boolean(form.title.trim()) && !codeBad && !prefixBad;
  const canSubmit = editId
    ? Boolean(cargoValid)
    : Boolean(cargoValid && form.owner_name.trim() && form.owner_phone.trim() && form.owner_password.length >= 6);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setModalErr('');
    setBusy(true);
    try {
      if (editId) {
        // slug неизменяем после создания — не отправляем.
        const body: Record<string, unknown> = {
          title: form.title.trim(),
          code: form.code.trim(),
          phone: form.phone.trim(),
          ...(prefixRaw ? { client_code_prefix: prefixRaw } : {}),
          address: form.address.trim(),
          is_active: form.is_active,
        };
        if (form.price_per_kg_kgs.trim()) body.price_per_kg_kgs = form.price_per_kg_kgs.trim();
        await patch(`/api/admin/cargos/${editId}/`, body);
        setBanner(t('ov.cargoUpdated'));
      } else {
        const body: Record<string, unknown> = {
          title: form.title.trim(),
          slug: form.slug.trim() || autoSlug(form.title) || `cargo-${Date.now().toString(36)}`,
          code: form.code.trim(),
          phone: form.phone.trim(),
          ...(prefixRaw ? { client_code_prefix: prefixRaw } : {}),
          address: form.address.trim(),
          owner_name: form.owner_name.trim(),
          owner_phone: form.owner_phone.trim(),
          owner_password: form.owner_password,
        };
        if (form.price_per_kg_kgs.trim()) body.price_per_kg_kgs = form.price_per_kg_kgs.trim();
        const r = await post<{ cargo: CargoRow; owner: { phone: string } }>('/api/admin/cargos/', body);
        setBanner(`«${r.cargo.title}» ${t('ov.createdOk')} ${r.owner.phone} ${t('ov.andPwd')}`);
      }
      setOpen(false);
      reload();
    } catch (e) {
      setModalErr(formError(e));
    } finally {
      setBusy(false);
    }
  }

  async function resetPassword() {
    if (!ownerId || newPwd.length < 6 || !editId) return;
    setPwdErr('');
    setPwdMsg('');
    setPwdBusy(true);
    try {
      await post(`/api/admin/cargos/${editId}/owner-password/`, { owner_id: Number(ownerId), password: newPwd });
      setPwdMsg(t('ov.pwdUpdated'));
      setNewPwd('');
    } catch (e) {
      setPwdErr(formError(e));
    } finally {
      setPwdBusy(false);
    }
  }

  if (forbidden)
    return (
      <div>
        <PageHeader title={t('ov.title')} />
        <Card pad>
          <EmptyState icon={<IconAlert size={26} />} title={t('ov.noAccess')} description={t('ov.noAccessDesc')} />
        </Card>
      </div>
    );

  if (err)
    return (
      <div>
        <PageHeader title={t('ov.title')} />
        <Alert variant="error">{err}</Alert>
      </div>
    );

  const tot = data?.totals;
  const tiles: { label: string; value: number | undefined; tone: Tone; icon: React.ReactNode }[] = [
    { label: t('ov.tCargos'), value: tot?.cargo_count, tone: 'blue', icon: <IconOverview size={19} /> },
    { label: t('ov.tActive'), value: tot?.active_cargo_count, tone: 'green', icon: <IconOverview size={19} /> },
    { label: t('ov.tClients'), value: tot?.user_count, tone: 'teal', icon: <IconStaff size={19} /> },
    { label: t('ov.tParcels'), value: tot?.parcel_count, tone: 'violet', icon: <IconBox size={19} /> },
    { label: t('ov.tOrders'), value: tot?.order_count, tone: 'indigo', icon: <IconTruck size={19} /> },
    { label: t('ov.tPickups'), value: tot?.pickup_point_count, tone: 'amber', icon: <IconOverview size={19} /> },
  ];

  const columns: Column<CargoRow>[] = [
    {
      key: 'cargo',
      header: t('common.cargo'),
      sortValue: (c) => c.title,
      render: (c) => (
        <div>
          <div className="strong">{c.title}</div>
          <div className="muted mono" style={{ fontSize: 12.5 }}>
            {c.slug}
            {c.code && ` · ${c.code}`}
          </div>
        </div>
      ),
    },
    {
      key: 'status',
      header: t('common.status'),
      sortValue: (c) => (c.is_active ? 0 : 1),
      render: (c) => (
        <Badge variant={c.is_active ? 'ok' : 'warn'} dot>
          {c.is_active ? t('common.active') : t('common.inactive')}
        </Badge>
      ),
    },
    { key: 'users', header: t('ov.colClients'), align: 'right', sortValue: (c) => c.users_count, render: (c) => <span className="num">{c.users_count}</span> },
    { key: 'parcels', header: t('ov.colParcels'), align: 'right', sortValue: (c) => c.parcels_count, render: (c) => <span className="num">{c.parcels_count}</span> },
    { key: 'orders', header: t('ov.colOrders'), align: 'right', sortValue: (c) => c.orders_count, render: (c) => <span className="num">{c.orders_count}</span> },
    { key: 'pickups', header: t('ov.colPickups'), align: 'right', sortValue: (c) => c.pickup_points_count, render: (c) => <span className="num">{c.pickup_points_count}</span> },
    {
      key: 'actions',
      header: '',
      align: 'right',
      render: (c) => (
        <div className="cluster gap-sm" style={{ justifyContent: 'flex-end', flexWrap: 'nowrap' }}>
          <Button variant="secondary" size="sm" onClick={(e) => { e.stopPropagation(); nav(`/cargo/${c.id}`); }}>
            {t('ov.open')}
          </Button>
          <Button variant="subtle" size="sm" onClick={(e) => { e.stopPropagation(); openEdit(c); }}>
            {t('common.edit')}
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title={t('ov.title')}
        subtitle={t('ov.subtitle')}
        actions={
          <Button onClick={openCreate} icon={<IconPlus size={18} />}>
            {t('ov.create')}
          </Button>
        }
      />

      {banner && <Alert variant="success">{banner}</Alert>}

      <StatGrid className="mb-lg">
        {tiles.map((tile) => (
          <Stat
            key={tile.label}
            icon={tile.icon}
            tone={tile.tone}
            label={tile.label}
            value={tile.value === undefined ? <Skeleton height={26} width="45%" /> : tile.value}
          />
        ))}
      </StatGrid>

      <Card>
        <CardHeader title={t('ov.byCargo')} actions={data && <Badge variant="plain">{data.per_cargo.length} {t('ov.cargosCount')}</Badge>} />
        <DataTable
          columns={columns}
          rows={data?.per_cargo}
          loading={loading}
          getRowKey={(c) => c.id}
          onRowClick={(c) => nav(`/cargo/${c.id}`)}
          initialSort={{ key: 'parcels', dir: 'desc' }}
          empty={
            <EmptyState
              icon={<IconOverview size={26} />}
              title={t('ov.emptyTitle')}
              action={
                <Button size="sm" onClick={openCreate} icon={<IconPlus size={16} />}>
                  {t('ov.create')}
                </Button>
              }
            />
          }
        />
      </Card>

      {open && (
        <Modal
          title={editId ? t('ov.editCargo') : t('ov.newCargo')}
          description={editId ? form.slug : t('ov.newCargoDesc')}
          onClose={() => setOpen(false)}
          footer={
            <>
              <Button variant="subtle" onClick={() => setOpen(false)}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" form="cargo-form" loading={busy} disabled={!canSubmit} icon={<IconCheck size={18} />}>
                {editId ? t('common.save') : t('common.create')}
              </Button>
            </>
          }
        >
          <form id="cargo-form" onSubmit={submit}>
            <div className="section-title" style={{ margin: '0 0 12px' }}>{t('ov.sectionCargo')}</div>
            <Field
              label={t('ov.name')}
              required
              helper={!editId && form.slug ? `${t('ov.idLabel')}: ${form.slug}` : undefined}
            >
              <Input
                value={form.title}
                onChange={(e) => {
                  set('title', e.target.value);
                  if (!editId) set('slug', autoSlug(e.target.value));
                }}
                placeholder="315CARGO Ош"
                autoFocus
              />
            </Field>
            <Field
              label={t('ov.clientPrefix')}
              className="mt-md"
              helper={!prefixBad ? t('ov.clientPrefixHint') : undefined}
              error={prefixBad ? t('ccode.prefixErr') : undefined}
              style={{ maxWidth: 280 }}
            >
              <Input
                value={form.client_code_prefix}
                onChange={(e) => set('client_code_prefix', e.target.value)}
                placeholder="X"
                autoComplete="off"
                invalid={prefixBad}
                suffix={prefixPreview}
              />
            </Field>
            <Field
              label={t('ov.code')}
              className="mt-md"
              helper={!codeBad ? t('ov.codeHint') : undefined}
              error={codeBad ? t('ov.codeErr') : undefined}
              style={{ maxWidth: 280 }}
            >
              <Input
                value={form.code}
                onChange={(e) => set('code', e.target.value)}
                placeholder="x69610"
                autoComplete="off"
                invalid={codeBad}
              />
            </Field>
            <div className="grid-2 mt-md">
              <Field label={t('ov.phone')}>
                <Input value={form.phone} onChange={(e) => set('phone', e.target.value)} placeholder="+996700000000" inputMode="tel" />
              </Field>
              <Field label={t('ov.tariff')}>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  inputMode="decimal"
                  suffix="сом / кг"
                  value={form.price_per_kg_kgs}
                  onChange={(e) => set('price_per_kg_kgs', e.target.value)}
                  placeholder="0.00"
                />
              </Field>
            </div>
            <Field label={t('ov.address')} className="mt-md">
              <Input value={form.address} onChange={(e) => set('address', e.target.value)} placeholder="Ош, ул. ..." />
            </Field>

            {editId ? (
              <>
                <div className="mt-md">
                  <Checkbox checked={form.is_active} onChange={(v) => set('is_active', v)}>
                    {t('ov.activeField')}
                  </Checkbox>
                </div>

                {invite && (
                  <>
                    <div className="section-title" style={{ margin: '22px 0 12px' }}>{t('invite.card')}</div>
                    <InviteLink url={invite.url} qr={invite.qr} />
                  </>
                )}

                <div className="section-title" style={{ margin: '22px 0 12px' }}>{t('ov.resetPwd')}</div>
                {admins.length === 0 ? (
                  <p className="muted" style={{ fontSize: 13 }}>{t('ov.noAdmins')}</p>
                ) : (
                  <div className="row" style={{ alignItems: 'flex-end' }}>
                    <Field label={t('ov.admin')} style={{ flex: 2 }}>
                      <Select value={ownerId} onChange={(e) => setOwnerId(e.target.value)}>
                        {admins.map((a) => (
                          <option key={a.id} value={a.id}>
                            {(a.full_name || t('ov.noName')) + ' · ' + a.phone}
                            {a.is_active ? '' : ` ${t('ov.disabled')}`}
                          </option>
                        ))}
                      </Select>
                    </Field>
                    <Field label={t('ov.newPwd')} style={{ flex: 2 }}>
                      <Input
                        type="password"
                        value={newPwd}
                        onChange={(e) => setNewPwd(e.target.value)}
                        placeholder={t('staff.pwdMin')}
                        autoComplete="new-password"
                        invalid={newPwd.length > 0 && newPwd.length < 6}
                      />
                    </Field>
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={resetPassword}
                      loading={pwdBusy}
                      disabled={!ownerId || newPwd.length < 6}
                    >
                      {t('an.reset')}
                    </Button>
                  </div>
                )}
                {pwdErr && <Alert variant="error">{pwdErr}</Alert>}
                {pwdMsg && <Alert variant="success">{pwdMsg}</Alert>}
              </>
            ) : (
              <>
                <div className="section-title" style={{ margin: '22px 0 12px' }}>{t('ov.sectionOwner')}</div>
                <div className="grid-2">
                  <Field label={t('ov.ownerName')} required>
                    <Input value={form.owner_name} onChange={(e) => set('owner_name', e.target.value)} placeholder="Имя Фамилия" />
                  </Field>
                  <Field label={t('ov.ownerPhone')} required>
                    <Input value={form.owner_phone} onChange={(e) => set('owner_phone', e.target.value)} placeholder="+996700000001" inputMode="tel" />
                  </Field>
                </div>
                <Field
                  label={t('ov.ownerPwd')}
                  required
                  className="mt-md"
                  error={pwdShort ? t('staff.pwdMinErr') : undefined}
                  helper={!pwdShort ? t('staff.pwdMin') : undefined}
                  style={{ maxWidth: 280 }}
                >
                  <Input
                    type="password"
                    value={form.owner_password}
                    onChange={(e) => set('owner_password', e.target.value)}
                    placeholder="••••••"
                    autoComplete="new-password"
                    invalid={pwdShort}
                  />
                </Field>
              </>
            )}

            {modalErr && <Alert variant="error">{modalErr}</Alert>}
          </form>
        </Modal>
      )}
    </div>
  );
}
