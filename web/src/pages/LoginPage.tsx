import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiError, post, setToken } from '../api';

export default function LoginPage() {
  const nav = useNavigate();
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr('');
    setBusy(true);
    try {
      const r = await post<{ access: string; user: any }>('/api/auth/token/', {
        login: login.trim(),
        password,
      });
      setToken(r.access);
      localStorage.setItem('who', r.user?.full_name || r.user?.phone || login);
      nav('/', { replace: true });
    } catch (e) {
      const ae = e as ApiError;
      setErr(ae.status === 400 ? 'Неверный логин или пароль' : ae.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="center">
      <form className="card login-card" onSubmit={submit}>
        <h1>Вход — 315CARGO</h1>
        <p className="muted" style={{ marginTop: -8, fontSize: 13 }}>
          Для сотрудников и администраторов
        </p>
        {err && <div className="error">{err}</div>}

        <label>Логин (телефон)</label>
        <input
          value={login}
          onChange={(e) => setLogin(e.target.value)}
          placeholder="+996700000000"
          autoComplete="username"
          autoFocus
        />

        <label>Пароль</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
          autoComplete="current-password"
        />

        <div style={{ marginTop: 18 }}>
          <button type="submit" disabled={busy || !login.trim() || !password} style={{ width: '100%' }}>
            {busy ? 'Вход…' : 'Войти'}
          </button>
        </div>
      </form>
    </div>
  );
}
