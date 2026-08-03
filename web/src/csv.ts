type Cell = string | number | null | undefined;

function esc(v: Cell): string {
  const s = v == null ? '' : String(v);
  return /[",\n\r;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCsv(rows: Cell[][]): string {
  return rows.map((r) => r.map(esc).join(',')).join('\r\n');
}

/** Скачать CSV. BOM добавлен, чтобы Excel корректно открыл кириллицу/中文. */
export function downloadCsv(filename: string, rows: Cell[][]) {
  const blob = new Blob(['﻿' + toCsv(rows)], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function today(): string {
  return new Date().toISOString().slice(0, 10);
}
