import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ApiError, get, post, setToken } from '../api';

type Cargo = { id: number; title: string; slug: string };

export default function LoginPage() {
  const nav = useNavigate();
  const [cargos, setCargos] = useState<Cargo[]>([]);
  const [cargoId, setCargoId] = useState('');
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [mode, setMode] = useState<'sms' | 'token'>('sms');
  const [token, setTok] = useState('');

  useEffect(() => {
    get<Cargo[]>('/api/cargo-companies/')
      .then((list) => {
        setCargos(list);
        if (list[0]) setCargoId(String(list[0].id));
      })
      .catch(() => setErr('Не удалось загрузить список карго'));
  }, []);

  async function sendCode() {
    setErr('');
    setBusy(true);
    try {
      await post('/api/auth/send-code/', { phone, cargo_id: Number(cargoId), purpose: 'login' });
      setSent(true);
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  async function verify() {
    setErr('');
    setBusy(true);
    try {
      const r = await post<{ access: string; user: any }>('/api/auth/verify-code/', {
        phone,
        code,
        cargo_id: Number(cargoId),
      });
      setToken(r.access);
      localStorage.setItem('who', r.user?.full_name || r.user?.phone || phone);
      nav('/', { replace: true });
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  function useTokenLogin() {
    if (!token.trim()) return;
    setToken(token.trim());
    localStorage.setItem('who', 'owner');
    nav('/', { replace: true });
  }

  return (
    <div className="center">
      <div className="card login-card">
        <h1>Вход — 315CARGO</h1>
        {err && <div className="error">{err}</div>}

        {mode === 'sms' ? (
          <>
            <label>Карго-центр</label>
            <select value={cargoId} onChange={(e) => setCargoId(e.target.value)}>
              {cargos.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
            </select>

            <label>Телефон</label>
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+996700000000"
            />

            {sent && (
              <>
                <label>SMS-код</label>
                <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="0000" />
              </>
            )}

            <div style={{ marginTop: 16 }}>
              {!sent ? (
                <button disabled={busy || !phone || !cargoId} onClick={sendCode}>
                  Отправить код
                </button>
              ) : (
                <button disabled={busy || !code} onClick={verify}>
                  Войти
                </button>
              )}
            </div>
            <p className="muted" style={{ marginTop: 14, fontSize: 13 }}>
              Владелец (супер-админ) без карго —{' '}
              <a onClick={() => setMode('token')} style={{ cursor: 'pointer' }}>
                войти по токену
              </a>
            </p>
          </>
        ) : (
          <>
            <label>Access-токен (JWT)</label>
            <input value={token} onChange={(e) => setTok(e.target.value)} placeholder="eyJhbGci..." />
            <div style={{ marginTop: 16 }}>
              <button disabled={!token.trim()} onClick={useTokenLogin}>
                Войти
              </button>
            </div>
            <p className="muted" style={{ marginTop: 14, fontSize: 13 }}>
              <a onClick={() => setMode('sms')} style={{ cursor: 'pointer' }}>
                ← вход по SMS
              </a>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
