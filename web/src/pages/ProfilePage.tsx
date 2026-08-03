import { useEffect, useState } from 'react';
import { get, patch, post, setRole, type ApiError } from '../api';
import { useI18n } from '../i18n';
import { IconCheck } from '../components/Icons';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  Field,
  formError,
  Input,
  PageHeader,
} from '../ui';

type Profile = {
  full_name: string;
  phone: string;
  cargo_title: string | null;
  pickup_point_title: string | null;
  is_cargo_admin: boolean;
  is_china_staff: boolean;
  is_superuser: boolean;
  is_staff: boolean;
  allowed_tabs: string[];
};

// Ключ вкладки → i18n-ключ подписи (зеркалит меню).
const TAB_NAV: Record<string, string> = {
  scan: 'nav.scan',
  issue: 'nav.issue',
  warehouse: 'nav.warehouse',
  china: 'nav.china',
  clients: 'nav.clients',
  delivery: 'nav.delivery',
  staff: 'nav.staff',
  pickup: 'nav.pickup',
  tariff: 'nav.tariff',
  delivery_tariff: 'nav.deliveryTariff',
  delivery_address: 'nav.deliveryAddress',
  analytics: 'nav.analytics',
  overview: 'nav.overview',
};

export default function ProfilePage() {
  const { t } = useI18n();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);

  // Данные
  const [name, setName] = useState('');
  const [savingName, setSavingName] = useState(false);
  const [nameErr, setNameErr] = useState('');
  const [nameMsg, setNameMsg] = useState('');

  // Пароль
  const [cur, setCur] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [savingPw, setSavingPw] = useState(false);
  const [pwErr, setPwErr] = useState('');
  const [pwMsg, setPwMsg] = useState('');

  useEffect(() => {
    get('/api/profile/')
      .then((u: Profile) => {
        setProfile(u);
        setName(u.full_name || '');
      })
      .catch((e) => setNameErr((e as ApiError).message))
      .finally(() => setLoading(false));
  }, []);

  const roleLabel = !profile
    ? ''
    : profile.is_china_staff && !profile.is_cargo_admin && !profile.is_superuser
      ? t('roles.china')
      : profile.is_superuser
        ? t('roles.owner')
        : profile.is_cargo_admin
          ? t('roles.cargoAdmin')
          : t('roles.staff');

  async function saveName(e: React.FormEvent) {
    e.preventDefault();
    setNameErr('');
    setNameMsg('');
    setSavingName(true);
    try {
      const u: Profile = await patch('/api/profile/', { full_name: name.trim() });
      setProfile(u);
      // Обновляем отображаемое имя в сайдбаре и роль.
      if (u.full_name || u.phone) localStorage.setItem('who', u.full_name || u.phone);
      setRole({
        is_china_staff: u.is_china_staff,
        is_cargo_admin: u.is_cargo_admin,
        is_superuser: u.is_superuser,
        is_staff: u.is_staff,
        allowed_tabs: u.allowed_tabs,
      });
      setNameMsg(t('profile.saved'));
    } catch (e) {
      setNameErr(formError(e));
    } finally {
      setSavingName(false);
    }
  }

  async function changePassword(e: React.FormEvent) {
    e.preventDefault();
    setPwErr('');
    setPwMsg('');
    if (next !== confirm) {
      setPwErr(t('profile.passwordMismatch'));
      return;
    }
    setSavingPw(true);
    try {
      await post('/api/profile/password/', {
        current_password: cur,
        new_password: next,
      });
      setPwMsg(t('profile.passwordChanged'));
      setCur('');
      setNext('');
      setConfirm('');
    } catch (e) {
      setPwErr(formError(e));
    } finally {
      setSavingPw(false);
    }
  }

  const canSaveName = name.trim() && name.trim() !== (profile?.full_name || '');
  const canChangePw = cur && next.length >= 6 && confirm;

  return (
    <div>
      <PageHeader title={t('profile.title')} subtitle={t('profile.subtitle')} />

      <div className="grid-2" style={{ alignItems: 'start' }}>
        <Card>
          <CardHeader title={t('profile.info')} />
          <div style={{ padding: '4px 16px 16px' }}>
            <form onSubmit={saveName}>
              <Field label={t('profile.name')}>
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={t('profile.namePlaceholder')}
                  disabled={loading}
                />
              </Field>

              <dl className="kv mt-md">
                <div>
                  <dt>{t('profile.phone')}</dt>
                  <dd className="num">{profile?.phone || t('common.notSet')}</dd>
                </div>
                <div>
                  <dt>{t('profile.role')}</dt>
                  <dd>{roleLabel || t('common.notSet')}</dd>
                </div>
                <div>
                  <dt>{t('profile.cargo')}</dt>
                  <dd>{profile?.cargo_title || t('common.notSet')}</dd>
                </div>
                <div>
                  <dt>{t('profile.pickup')}</dt>
                  <dd>{profile?.pickup_point_title || t('common.notSet')}</dd>
                </div>
              </dl>

              {profile && profile.allowed_tabs.length > 0 && (
                <div className="mt-md">
                  <div className="nav-group-label" style={{ padding: '0 0 6px' }}>
                    {t('profile.tabs')}
                  </div>
                  <div className="cluster gap-sm" style={{ flexWrap: 'wrap' }}>
                    {profile.allowed_tabs.map((tab) => (
                      <Badge key={tab} variant="blue">
                        {TAB_NAV[tab] ? t(TAB_NAV[tab]) : tab}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {nameErr && <Alert variant="error">{nameErr}</Alert>}
              {nameMsg && <Alert variant="success">{nameMsg}</Alert>}

              <div className="mt-md">
                <Button
                  type="submit"
                  loading={savingName}
                  disabled={!canSaveName}
                  icon={<IconCheck size={18} />}
                >
                  {t('common.save')}
                </Button>
              </div>
            </form>
          </div>
        </Card>

        <Card>
          <CardHeader title={t('profile.password')} />
          <div style={{ padding: '4px 16px 16px' }}>
            <form onSubmit={changePassword}>
              <Field label={t('profile.currentPassword')}>
                <Input
                  type="password"
                  autoComplete="current-password"
                  value={cur}
                  onChange={(e) => setCur(e.target.value)}
                />
              </Field>
              <Field label={t('profile.newPassword')} helper={t('profile.passwordHint')} className="mt-md">
                <Input
                  type="password"
                  autoComplete="new-password"
                  value={next}
                  onChange={(e) => setNext(e.target.value)}
                />
              </Field>
              <Field label={t('profile.confirmPassword')} className="mt-md">
                <Input
                  type="password"
                  autoComplete="new-password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                />
              </Field>

              {pwErr && <Alert variant="error">{pwErr}</Alert>}
              {pwMsg && <Alert variant="success">{pwMsg}</Alert>}

              <div className="mt-md">
                <Button type="submit" loading={savingPw} disabled={!canChangePw}>
                  {t('profile.changePassword')}
                </Button>
              </div>
            </form>
          </div>
        </Card>
      </div>
    </div>
  );
}
