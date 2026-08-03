import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiError, post, setToken, setRole } from '../api';
import { useI18n } from '../i18n';
import LangSwitcher from '../components/LangSwitcher';
import { Alert, Button, Field, Input } from '../ui';

export default function LoginPage() {
  const nav = useNavigate();
  const { t } = useI18n();
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const canSubmit = login.trim().length > 0 && password.length > 0;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setErr('');
    setBusy(true);
    try {
      const r = await post<{ access: string; user: any }>('/api/auth/token/', {
        login: login.trim(),
        password,
      });
      setToken(r.access);
      localStorage.setItem('who', r.user?.full_name || r.user?.phone || login);
      setRole({
        is_china_staff: r.user?.is_china_staff,
        is_cargo_admin: r.user?.is_cargo_admin,
        is_superuser: r.user?.is_superuser,
        is_staff: r.user?.is_staff,
        allowed_tabs: r.user?.allowed_tabs,
      });
      nav('/', { replace: true });
    } catch (e) {
      const ae = e as ApiError;
      setErr(ae.status === 400 || ae.status === 401 ? t('login.error') : ae.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <form className="auth-card" onSubmit={submit}>
        <div className="auth-brand">
          <div className="mark">315</div>
          <div className="t">
            315CARGO
            <small>{t('login.subtitle')}</small>
          </div>
          <span className="grow" />
          <LangSwitcher />
        </div>

        {err && <Alert variant="error">{err}</Alert>}

        <Field label={t('login.loginLabel')} htmlFor="login" className="mt-lg">
          <Input
            id="login"
            value={login}
            onChange={(e) => setLogin(e.target.value)}
            placeholder="+996700000000"
            autoComplete="username"
            inputMode="tel"
            invalid={Boolean(err)}
            autoFocus
          />
        </Field>

        <Field label={t('login.passwordLabel')} htmlFor="pwd" className="mt-md">
          <Input
            id="pwd"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            autoComplete="current-password"
            invalid={Boolean(err)}
          />
        </Field>

        <Button
          type="submit"
          block
          loading={busy}
          disabled={!canSubmit}
          className="mt-lg"
          style={{ padding: 12 }}
        >
          {busy ? t('login.submitting') : t('login.submit')}
        </Button>

        <p className="helper" style={{ textAlign: 'center', marginTop: 16 }}>
          {t('login.note')}
        </p>
      </form>
    </div>
  );
}
