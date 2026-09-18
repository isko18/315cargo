import { useId, useState } from 'react';
import type { ReactNode } from 'react';
import { IconFilter } from '../components/Icons';
import { Card, CardBody } from './Card';

/**
 * Блок фильтров, который на телефоне убирается под кнопку.
 *
 * Развёрнутые фильтры на узком экране занимают целый экран: до первой строки
 * данных приходится пролистать поиск, статус, даты и переключатели. На
 * широком экране места хватает, поэтому там панель всегда открыта и кнопки
 * просто нет — прятать нечего.
 *
 * `activeCount` показывается на кнопке: свёрнутый фильтр иначе выглядит как
 * пропавшие данные — список короткий, а почему, не видно.
 */
export default function FilterPanel({
  children,
  activeCount = 0,
  label,
}: {
  children: ReactNode;
  activeCount?: number;
  label: string;
}) {
  const [open, setOpen] = useState(false);
  const bodyId = useId();

  return (
    <Card className="filter-panel">
      <button
        type="button"
        className="filter-panel-toggle"
        aria-expanded={open}
        aria-controls={bodyId}
        onClick={() => setOpen((v) => !v)}
      >
        <IconFilter size={18} />
        <span>{label}</span>
        {activeCount > 0 && <span className="filter-count">{activeCount}</span>}
        <span className="grow" />
        <span className={`filter-panel-caret ${open ? 'open' : ''}`} aria-hidden="true" />
      </button>
      <CardBody className={open ? '' : 'is-collapsed'} id={bodyId}>
        {children}
      </CardBody>
    </Card>
  );
}
