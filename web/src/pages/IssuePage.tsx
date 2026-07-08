import { useRef, useState } from 'react';
import { ApiError, get, post } from '../api';

type Parcel = {
  id: number;
  track_number: string;
  status: string;
  status_display_name: string;
  client_code: string | null;
  product_title?: string | null;
  product_image?: string | null;
};

// Статусы, которые уже нельзя выдавать (финальные).
const FINAL = new Set(['issued', 'cancelled']);

export default function IssuePage() {
  const [clientCode, setClientCode] = useState('');
  const [cargo, setCargo] = useState('');
  const [parcels, setParcels] = useState<Parcel[] | null>(null);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  function extractList(data: any): Parcel[] {
    return (data?.results ?? data) as Parcel[];
  }

  async function load() {
    const cc = clientCode.trim();
    if (!cc || busy) return;
    setErr('');
    setMsg('');
    setBusy(true);
    try {
      const data = await get(`/api/parcels/?client_code=${encodeURIComponent(cc)}`);
      const list = extractList(data);
      setParcels(list);
      // по умолчанию выбираем все, что ещё можно выдать
      setSel(new Set(list.filter((p) => !FINAL.has(p.status)).map((p) => p.id)));
    } catch (e) {
      setErr((e as ApiError).message);
      setParcels(null);
    } finally {
      setBusy(false);
    }
  }

  function toggle(id: number) {
    setSel((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  }

  async function issue() {
    if (!parcels || sel.size === 0 || busy) return;
    setErr('');
    setMsg('');
    setBusy(true);
    const chosen = parcels.filter((p) => sel.has(p.id) && !FINAL.has(p.status));
    let ok = 0;
    const errors: string[] = [];
    for (const p of chosen) {
      try {
        const body: Record<string, unknown> = { track_number: p.track_number, status: 'issued' };
        if (cargo.trim()) body.cargo = Number(cargo.trim());
        await post('/api/parcels/scan/', body);
        ok += 1;
      } catch (e) {
        errors.push(`${p.track_number}: ${(e as ApiError).message}`);
      }
    }
    setMsg(`Выдано: ${ok} из ${chosen.length}`);
    if (errors.length) setErr(errors.join('\n'));
    await load(); // обновить статусы
    setBusy(false);
  }

  const issuable = parcels?.filter((p) => !FINAL.has(p.status)) ?? [];

  return (
    <div>
      <h1>Выдача товаров клиенту</h1>

      <div className="card">
        <div className="row">
          <div style={{ flex: 3 }}>
            <label>Код клиента (или скан QR клиента)</label>
            <input
              ref={inputRef}
              className="scan-input"
              value={clientCode}
              onChange={(e) => setClientCode(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && load()}
              placeholder="C1234567"
              autoComplete="off"
            />
          </div>
          <button onClick={load} disabled={busy || !clientCode.trim()}>
            Найти
          </button>
        </div>
        <label style={{ marginTop: 8 }}>Карго ID (только для супер-админа)</label>
        <input
          value={cargo}
          onChange={(e) => setCargo(e.target.value)}
          placeholder="оставь пустым, если ты оператор карго"
          style={{ maxWidth: 320 }}
        />
        {err && <div className="error" style={{ whiteSpace: 'pre-wrap' }}>{err}</div>}
        {msg && <div className="ok" style={{ marginTop: 8 }}>{msg}</div>}
      </div>

      {parcels && (
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <h2 style={{ margin: 0 }}>
              Посылок: {parcels.length} · к выдаче: {issuable.length}
            </h2>
            <span className="spacer" style={{ flex: 1 }} />
            <button onClick={issue} disabled={busy || sel.size === 0}>
              Выдать выбранные ({sel.size})
            </button>
          </div>

          {parcels.length === 0 ? (
            <p className="muted">У клиента нет посылок.</p>
          ) : (
            <table style={{ marginTop: 12 }}>
              <thead>
                <tr>
                  <th style={{ width: 36 }}></th>
                  <th>Товар</th>
                  <th>Трек</th>
                  <th>Статус</th>
                </tr>
              </thead>
              <tbody>
                {parcels.map((p) => {
                  const done = FINAL.has(p.status);
                  return (
                    <tr key={p.id} style={done ? { opacity: 0.55 } : undefined}>
                      <td>
                        <input
                          type="checkbox"
                          style={{ width: 18 }}
                          disabled={done}
                          checked={sel.has(p.id)}
                          onChange={() => toggle(p.id)}
                        />
                      </td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          {p.product_image && (
                            <img
                              src={p.product_image}
                              alt=""
                              style={{ width: 36, height: 36, borderRadius: 6, objectFit: 'cover' }}
                            />
                          )}
                          <span>{p.product_title || '—'}</span>
                        </div>
                      </td>
                      <td>{p.track_number}</td>
                      <td>
                        <span className={`badge ${p.status === 'issued' ? 'ok' : ''}`}>
                          {p.status_display_name}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
