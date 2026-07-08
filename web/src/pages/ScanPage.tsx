import { useEffect, useRef, useState } from 'react';
import { ApiError, post } from '../api';

const STATUSES: { value: string; label: string }[] = [
  { value: 'arrived_china_warehouse', label: 'Прибыл на склад в Китае' },
  { value: 'sent_to_kyrgyzstan', label: 'Отправлен в Кыргызстан' },
  { value: 'arrived_kyrgyzstan', label: 'Прибыл в Кыргызстан' },
  { value: 'at_pickup_point', label: 'В ПВЗ' },
  { value: 'issued', label: 'Выдан клиенту' },
];

const RESULT_LABEL: Record<string, string> = {
  updated: 'обновлён',
  created_from_order: 'создан из заказа',
  created_pending: 'создан (без клиента)',
};

type Parcel = {
  id: number;
  track_number: string;
  status: string;
  status_display_name: string;
  client_code: string | null;
  user: number | null;
};

type Entry = { result: string; parcel: Parcel };

export default function ScanPage() {
  const [track, setTrack] = useState('');
  const [status, setStatus] = useState(STATUSES[0].value);
  const [cargo, setCargo] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [log, setLog] = useState<Entry[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  async function scan() {
    const tn = track.trim();
    if (!tn || busy) return;
    setErr('');
    setBusy(true);
    try {
      const body: Record<string, unknown> = { track_number: tn, status };
      if (cargo.trim()) body.cargo = Number(cargo.trim());
      const r = await post<Entry>('/api/parcels/scan/', body);
      setLog((l) => [r, ...l]);
      setTrack('');
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  }

  async function assign(entryIdx: number, clientCode: string) {
    const cc = clientCode.trim();
    if (!cc) return;
    const p = log[entryIdx].parcel;
    setErr('');
    try {
      const updated = await post<Parcel>(`/api/parcels/${p.id}/assign/`, { client_code: cc });
      setLog((l) => l.map((e, i) => (i === entryIdx ? { ...e, parcel: updated } : e)));
    } catch (e) {
      setErr((e as ApiError).message);
    }
  }

  return (
    <div>
      <h1>Приём посылок по штрих-коду</h1>

      <div className="card">
        <div className="row">
          <div style={{ flex: 3 }}>
            <label>Штрих-код / трек-номер (сканер + Enter)</label>
            <input
              ref={inputRef}
              className="scan-input"
              value={track}
              onChange={(e) => setTrack(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && scan()}
              placeholder="отсканируйте штрих-код…"
              autoComplete="off"
            />
          </div>
          <div style={{ flex: 2 }}>
            <label>Статус</label>
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              {STATUSES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          <button onClick={scan} disabled={busy || !track.trim()}>
            Принять
          </button>
        </div>
        <label style={{ marginTop: 8 }}>
          Карго ID (только для супер-админа без своего карго)
        </label>
        <input
          value={cargo}
          onChange={(e) => setCargo(e.target.value)}
          placeholder="напр. 1 — оставь пустым, если ты оператор карго"
          style={{ maxWidth: 320 }}
        />
        {err && <div className="error">{err}</div>}
      </div>

      {log.length > 0 && (
        <div className="card">
          <h2>Отсканировано за сессию: {log.length}</h2>
          <table>
            <thead>
              <tr>
                <th>Трек</th>
                <th>Результат</th>
                <th>Статус</th>
                <th>Клиент</th>
              </tr>
            </thead>
            <tbody>
              {log.map((e, i) => (
                <tr key={`${e.parcel.id}-${i}`}>
                  <td>{e.parcel.track_number}</td>
                  <td>
                    <span className="badge">{RESULT_LABEL[e.result] || e.result}</span>
                  </td>
                  <td>{e.parcel.status_display_name}</td>
                  <td>
                    {e.parcel.user ? (
                      <span className="badge ok">{e.parcel.client_code}</span>
                    ) : (
                      <AssignInline onAssign={(cc) => assign(i, cc)} />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function AssignInline({ onAssign }: { onAssign: (code: string) => void }) {
  const [code, setCode] = useState('');
  return (
    <div style={{ display: 'flex', gap: 6 }}>
      <input
        value={code}
        onChange={(e) => setCode(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && onAssign(code)}
        placeholder="код клиента"
        style={{ padding: '6px 8px', fontSize: 13 }}
      />
      <button
        className="ghost"
        style={{ padding: '6px 10px' }}
        onClick={() => onAssign(code)}
      >
        Привязать
      </button>
    </div>
  );
}
