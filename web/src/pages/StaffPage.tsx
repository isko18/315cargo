import { useEffect, useState } from 'react';
import { ApiError, get, patch, post } from '../api';

type Staff = {
  id: number;
  phone: string;
  full_name: string;
  cargo: number | null;
  cargo_title: string | null;
  is_cargo_admin: boolean;
  is_active: boolean;
};
type Cargo = { id: number; title: string };

export default function StaffPage() {
  const [list, setList] = useState<Staff[]>([]);
  const [cargos, setCargos] = useState<Cargo[]>([]);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);

  const [phone, setPhone] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [isAdmin, setIsAdmin] = useState(false);
  const [cargo, setCargo] = useState('');

  function extract(d: any): Staff[] {
    return (d?.results ?? d) as Staff[];
  }

  async function reload() {
    try {
      setList(extract(await get('/api/manage/staff/')));
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  useEffect(() => {
    reload();
    get<Cargo[]>('/api/cargo-companies/').then(setCargos).catch(() => {});
  }, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setErr('');
    setMsg('');
    setBusy(true);
    try {
      const body: Record<string, unknown> = {
        phone: phone.trim(),
        full_name: fullName.trim(),
        password,
        is_cargo_admin: isAdmin,
      };
      if (cargo) body.cargo = Number(cargo);
      const created = await post<Staff>('/api/manage/staff/', body);
      setMsg(`Сотрудник ${created.phone} создан`);
      setPhone('');
      setFullName('');
      setPassword('');
      setIsAdmin(false);
      await reload();
    } catch (e) {
      const ae = e as ApiError;
      setErr(
        ae.data && typeof ae.data === 'object'
          ? Object.entries(ae.data)
              .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
              .join('; ')
          : ae.message,
      );
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

  return (
    <div>
      <h1>Сотрудники</h1>

      <div className="card">
        <h2>Добавить сотрудника</h2>
        <form onSubmit={create}>
          <div className="row">
            <div>
              <label>Телефон (логин)</label>
              <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+996700000000" />
            </div>
            <div>
              <label>ФИО</label>
              <input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Имя Фамилия" />
            </div>
            <div>
              <label>Пароль (мин. 6)</label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••" />
            </div>
          </div>
          <div className="row" style={{ marginTop: 8, alignItems: 'center' }}>
            <div>
              <label>Карго (только для супер-владельца)</label>
              <select value={cargo} onChange={(e) => setCargo(e.target.value)}>
                <option value="">— моё карго —</option>
                {cargos.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.title}
                  </option>
                ))}
              </select>
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text)', margin: 0 }}>
              <input
                type="checkbox"
                style={{ width: 18 }}
                checked={isAdmin}
                onChange={(e) => setIsAdmin(e.target.checked)}
              />
              Администратор карго (полный доступ)
            </label>
            <button type="submit" disabled={busy || !phone.trim() || password.length < 6}>
              Создать
            </button>
          </div>
          {err && <div className="error">{err}</div>}
          {msg && <div className="ok" style={{ marginTop: 8 }}>{msg}</div>}
        </form>
      </div>

      <div className="card">
        <h2>Список ({list.length})</h2>
        <table>
          <thead>
            <tr>
              <th>Телефон</th>
              <th>ФИО</th>
              <th>Карго</th>
              <th>Роль</th>
              <th>Статус</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {list.map((s) => (
              <tr key={s.id} style={s.is_active ? undefined : { opacity: 0.5 }}>
                <td>{s.phone}</td>
                <td>{s.full_name || '—'}</td>
                <td>{s.cargo_title || '—'}</td>
                <td>
                  <span className="badge">{s.is_cargo_admin ? 'админ карго' : 'оператор'}</span>
                </td>
                <td>
                  <span className={`badge ${s.is_active ? 'ok' : 'warn'}`}>
                    {s.is_active ? 'активен' : 'выключен'}
                  </span>
                </td>
                <td>
                  <button className="ghost" style={{ padding: '5px 10px' }} onClick={() => toggleActive(s)}>
                    {s.is_active ? 'Выключить' : 'Включить'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
