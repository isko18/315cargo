import { useEffect, useState } from 'react';
import { ApiError, get } from '../api';

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
  is_active: boolean;
  users_count: number;
  parcels_count: number;
  orders_count: number;
  pickup_points_count: number;
};
type Overview = { totals: Totals; per_cargo: CargoRow[] };

export default function OverviewPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [err, setErr] = useState('');

  useEffect(() => {
    get<Overview>('/api/admin/overview/')
      .then(setData)
      .catch((e: ApiError) =>
        setErr(
          e.status === 403
            ? 'Нет доступа: обзор всех карго доступен только владельцу (супер-админу).'
            : e.message,
        ),
      );
  }, []);

  if (err) return <div className="error">{err}</div>;
  if (!data) return <p className="muted">Загрузка…</p>;

  const t = data.totals;
  const tiles: [string, number][] = [
    ['Карго-центров', t.cargo_count],
    ['Активных карго', t.active_cargo_count],
    ['Клиентов', t.user_count],
    ['Посылок', t.parcel_count],
    ['Заказов', t.order_count],
    ['ПВЗ', t.pickup_point_count],
  ];

  return (
    <div>
      <h1>Все карго — обзор владельца</h1>

      <div className="stats" style={{ marginBottom: 18 }}>
        {tiles.map(([lbl, num]) => (
          <div className="stat" key={lbl}>
            <div className="num">{num}</div>
            <div className="lbl">{lbl}</div>
          </div>
        ))}
      </div>

      <div className="card">
        <h2>По карго-центрам</h2>
        <table>
          <thead>
            <tr>
              <th>Карго</th>
              <th>Статус</th>
              <th>Клиенты</th>
              <th>Посылки</th>
              <th>Заказы</th>
              <th>ПВЗ</th>
            </tr>
          </thead>
          <tbody>
            {data.per_cargo.map((c) => (
              <tr key={c.id}>
                <td>
                  <strong>{c.title}</strong>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {c.slug}
                  </div>
                </td>
                <td>
                  <span className={`badge ${c.is_active ? 'ok' : 'warn'}`}>
                    {c.is_active ? 'активен' : 'выключен'}
                  </span>
                </td>
                <td>{c.users_count}</td>
                <td>{c.parcels_count}</td>
                <td>{c.orders_count}</td>
                <td>{c.pickup_points_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
