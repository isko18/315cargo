import { useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { IconSort, IconSortAsc, IconSortDesc } from '../components/Icons';
import Skeleton from './Skeleton';

export type Align = 'left' | 'right' | 'center';

export interface Column<T> {
  key: string;
  header: ReactNode;
  align?: Align;
  width?: number | string;
  render: (row: T) => ReactNode;
  /** Возврат значения включает сортировку по колонке. */
  sortValue?: (row: T) => string | number | null | undefined;
}

export interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[] | null | undefined;
  getRowKey: (row: T, index: number) => string | number;
  loading?: boolean;
  onRowClick?: (row: T) => void;
  rowClassName?: (row: T) => string | undefined;
  empty?: ReactNode;
  skeletonRows?: number;
  initialSort?: { key: string; dir: 'asc' | 'desc' };
}

/**
 * Единая таблица данных: сортировка по колонкам (client-side), скелетоны на
 * загрузке, пустое состояние, кликабельные строки, выравнивание колонок.
 */
export default function DataTable<T>({
  columns,
  rows,
  getRowKey,
  loading = false,
  onRowClick,
  rowClassName,
  empty,
  skeletonRows = 6,
  initialSort,
}: DataTableProps<T>) {
  const [sort, setSort] = useState<{ key: string; dir: 'asc' | 'desc' } | null>(initialSort ?? null);

  const sorted = useMemo(() => {
    if (!rows || !sort) return rows ?? [];
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sortValue) return rows;
    const dir = sort.dir === 'asc' ? 1 : -1;
    return [...rows].sort((a, b) => {
      const va = col.sortValue!(a);
      const vb = col.sortValue!(b);
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir;
      return String(va).localeCompare(String(vb), undefined, { numeric: true }) * dir;
    });
  }, [rows, sort, columns]);

  function toggleSort(key: string) {
    setSort((cur) => {
      if (cur?.key !== key) return { key, dir: 'asc' };
      if (cur.dir === 'asc') return { key, dir: 'desc' };
      return null; // третий клик — сброс
    });
  }

  const alignClass = (a?: Align) => (a === 'right' ? 'align-right' : a === 'center' ? 'align-center' : '');

  // Пустое состояние показываем вместо таблицы (без шапки колонок).
  if (!loading && rows != null && rows.length === 0 && empty) {
    return <>{empty}</>;
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((c) => {
              const isSorted = sort?.key === c.key;
              return (
                <th
                  key={c.key}
                  style={{ width: c.width }}
                  className={`${alignClass(c.align)} ${c.sortValue ? 'sortable' : ''} ${isSorted ? 'sorted' : ''}`}
                  onClick={c.sortValue ? () => toggleSort(c.key) : undefined}
                  aria-sort={isSorted ? (sort!.dir === 'asc' ? 'ascending' : 'descending') : undefined}
                >
                  <span className="th-inner">
                    {c.header}
                    {c.sortValue && (
                      <span className="sort-ind">
                        {!isSorted ? (
                          <IconSort size={13} />
                        ) : sort!.dir === 'asc' ? (
                          <IconSortAsc size={13} />
                        ) : (
                          <IconSortDesc size={13} />
                        )}
                      </span>
                    )}
                  </span>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {loading && (!rows || rows.length === 0)
            ? Array.from({ length: skeletonRows }).map((_, i) => (
                <tr key={`sk-${i}`}>
                  {columns.map((c) => (
                    <td key={c.key} className={alignClass(c.align)}>
                      <Skeleton height={14} width={c.align === 'right' ? '50%' : '75%'} />
                    </td>
                  ))}
                </tr>
              ))
            : sorted.map((row, i) => (
                <tr
                  key={getRowKey(row, i)}
                  className={`${onRowClick ? 'clickable' : ''} ${rowClassName?.(row) ?? ''}`}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                >
                  {columns.map((c) => (
                    <td key={c.key} className={alignClass(c.align)}>
                      {c.render(row)}
                    </td>
                  ))}
                </tr>
              ))}
        </tbody>
      </table>
    </div>
  );
}
