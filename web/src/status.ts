// Единая карта статусов посылки: подпись + тон (класс цвета).
// Используется в приёмке, выдаче и аналитике, чтобы цвет статуса был
// одинаковым во всём приложении.

export type Tone =
  | 'gray'
  | 'indigo'
  | 'amber'
  | 'blue'
  | 'cyan'
  | 'violet'
  | 'teal'
  | 'green'
  | 'red';

export const STATUS: Record<string, { label: string; tone: Tone }> = {
  created: { label: 'Оформлен', tone: 'gray' },
  purchased: { label: 'Выкуплен', tone: 'indigo' },
  waiting_china_warehouse: { label: 'Ожидается в Китае', tone: 'amber' },
  arrived_china_warehouse: { label: 'На складе в Китае', tone: 'amber' },
  in_storage: { label: 'На хранении', tone: 'gray' },
  sent_to_kyrgyzstan: { label: 'Отправлен, в пути', tone: 'blue' },
  in_transit: { label: 'В пути', tone: 'teal' },
  arrived_kyrgyzstan: { label: 'Прибыл в КР', tone: 'cyan' },
  processing: { label: 'Обработка', tone: 'indigo' },
  arrived_topa: { label: 'Прибыл в Топа', tone: 'blue' },
  at_pickup_point: { label: 'В ПВЗ', tone: 'violet' },
  city_delivery: { label: 'Доставка по городу', tone: 'teal' },
  delivered: { label: 'Доставлен', tone: 'green' },
  issued: { label: 'Выдан клиенту', tone: 'green' },
  cancelled: { label: 'Отменён', tone: 'red' },
};

export function statusMeta(key: string): { label: string; tone: Tone } {
  return STATUS[key] ?? { label: key, tone: 'gray' };
}

// Статусы, после которых посылку уже нельзя выдавать (финальные).
export const FINAL = new Set(['issued', 'cancelled']);
