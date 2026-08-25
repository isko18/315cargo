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
  /**
   * Подпись ячейки в карточном режиме (узкий экран). По умолчанию берётся
   * `header`, если он строка. Пустая строка убирает подпись — для колонок
   * с чекбоксом или кнопками действий.
   */
  cardLabel?: string;
  /**
   * Роль колонки в карточном режиме: `title` — заголовок карточки на всю
   * ширину без подписи, `corner` — управляющий элемент в углу карточки
   * (чекбокс выбора), `hide` — не показывать (второстепенные данные, из-за
   * которых карточка растёт на пол-экрана). По умолчанию обычная строка.
   */
  mobile?: 'title' | 'hide' | 'corner';
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
  /** Превращать строки в карточки на узких экранах (по умолчанию — да). */
  mobileCards?: boolean;
}

/**
 * Единая таблица данных: сортировка по колонкам (client-side), скелетоны на
 * загрузке, пустое состояние, кликабельные строки, выравнивание колонок.
 *
 * На узких экранах CSS раскладывает строки карточками (`.table-wrap.as-cards`).
 * Поскольку это меняет `display`, роли таблицы проставлены явно — иначе
 * скринридер потерял бы структуру.
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
  mobileCards = true,
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
  const cardLabel = (c: Column<T>) => c.cardLabel ?? (typeof c.header === 'string' ? c.header : '');
  // Классы карточного режима навешиваем всегда — их читает только CSS узкого
  // экрана, на десктопе они ни на что не влияют.
  const cellClass = (c: Column<T>) =>
    [alignClass(c.align), c.mobile ? `dt-${c.mobile}` : ''].filter(Boolean).join(' ');

  // Пустое состояние показываем вместо таблицы (без шапки колонок).
  if (!loading && rows != null && rows.length === 0 && empty) {
    return <>{empty}</>;
  }

  return (
    <div className={`table-wrap ${mobileCards ? 'as-cards' : ''}`}>
      <table role="table">
        <thead>
          <tr role="row">
            {columns.map((c) => {
              const isSorted = sort?.key === c.key;
              const indicator = c.sortValue && (
                <span className="sort-ind">
                  {!isSorted ? (
                    <IconSort size={13} />
                  ) : sort!.dir === 'asc' ? (
                    <IconSortAsc size={13} />
                  ) : (
                    <IconSortDesc size={13} />
                  )}
                </span>
              );
              return (
                <th
                  key={c.key}
                  role="columnheader"
                  scope="col"
                  style={{ width: c.width }}
                  className={`${alignClass(c.align)} ${isSorted ? 'sorted' : ''}`}
                  aria-sort={
                    c.sortValue
                      ? isSorted
                        ? sort!.dir === 'asc'
                          ? 'ascending'
                          : 'descending'
                        : 'none'
                      : undefined
                  }
                >
                  {/* Сортировка — настоящая кнопка: доступна с клавиатуры. */}
                  {c.sortValue ? (
                    <button type="button" className="th-inner" onClick={() => toggleSort(c.key)}>
                      {c.header}
                      {indicator}
                    </button>
                  ) : (
                    <span className="th-inner">{c.header}</span>
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {loading && (!rows || rows.length === 0)
            ? Array.from({ length: skeletonRows }).map((_, i) => (
                <tr key={`sk-${i}`} role="row">
                  {columns.map((c) => (
                    <td key={c.key} role="cell" data-label={cardLabel(c)} className={cellClass(c)}>
                      <Skeleton height={14} width={c.align === 'right' ? '50%' : '75%'} />
                    </td>
                  ))}
                </tr>
              ))
            : sorted.map((row, i) => (
                <tr
                  key={getRowKey(row, i)}
                  role="row"
                  className={`${onRowClick ? 'clickable' : ''} ${rowClassName?.(row) ?? ''}`}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  // Кликабельная строка должна открываться и с клавиатуры.
                  tabIndex={onRowClick ? 0 : undefined}
                  onKeyDown={
                    onRowClick
                      ? (e) => {
                          if (e.target !== e.currentTarget) return;
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            onRowClick(row);
                          }
                        }
                      : undefined
                  }
                >
                  {columns.map((c) => (
                    <td key={c.key} role="cell" data-label={cardLabel(c)} className={cellClass(c)}>
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
