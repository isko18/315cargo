import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DataTable, { type Column } from './DataTable';

type Row = { id: number; name: string; n: number };
const rows: Row[] = [
  { id: 1, name: 'B', n: 2 },
  { id: 2, name: 'A', n: 3 },
  { id: 3, name: 'C', n: 1 },
];
const columns: Column<Row>[] = [
  { key: 'name', header: 'Имя', render: (r) => r.name },
  { key: 'n', header: 'N', align: 'right', sortValue: (r) => r.n, render: (r) => String(r.n) },
];

function rowTexts() {
  return screen
    .getAllByRole('row')
    .slice(1) // без шапки
    .map((tr) => within(tr).getAllByRole('cell')[0].textContent);
}

describe('DataTable', () => {
  it('рендерит строки', () => {
    render(<DataTable columns={columns} rows={rows} getRowKey={(r) => r.id} />);
    expect(rowTexts()).toEqual(['B', 'A', 'C']);
  });

  it('сортирует по клику на заголовок (asc, потом desc)', async () => {
    render(<DataTable columns={columns} rows={rows} getRowKey={(r) => r.id} />);
    const header = screen.getByText('N');
    await userEvent.click(header); // asc по n: 1,2,3 → C,B,A
    expect(rowTexts()).toEqual(['C', 'B', 'A']);
    await userEvent.click(header); // desc: 3,2,1 → A,B,C
    expect(rowTexts()).toEqual(['A', 'B', 'C']);
  });

  it('показывает пустое состояние', () => {
    render(
      <DataTable columns={columns} rows={[]} getRowKey={(r) => r.id} empty={<div>Пусто</div>} />,
    );
    expect(screen.getByText('Пусто')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('клик по строке вызывает onRowClick', async () => {
    const onRowClick = vi.fn();
    render(<DataTable columns={columns} rows={rows} getRowKey={(r) => r.id} onRowClick={onRowClick} />);
    await userEvent.click(screen.getByText('B'));
    expect(onRowClick).toHaveBeenCalledWith(rows[0]);
  });
});
