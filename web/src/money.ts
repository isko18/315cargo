/**
 * Валюта панели — киргизский сом. Единая точка форматирования сумм:
 * тариф, стоимость посылки, итог на выдаче, выручка в аналитике.
 */
export const CURRENCY = 'сом';

/** «1234.5» → «1 234.50 сом». Пустое/нечисловое значение → «—». */
export function money(value: number | string | null | undefined): string {
  const n = typeof value === 'number' ? value : parseFloat(value ?? '');
  if (!Number.isFinite(n)) return '—';
  return `${amount(n)} ${CURRENCY}`;
}

/** Сумма без валюты, с разделителем тысяч: 50000 → «50 000.00». */
export function amount(n: number): string {
  const [int, frac] = n.toFixed(2).split('.');
  return `${int.replace(/\B(?=(\d{3})+(?!\d))/g, ' ')}.${frac}`;
}
