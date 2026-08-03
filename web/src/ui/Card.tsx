import type { ReactNode } from 'react';

export function Card({
  children,
  pad = false,
  className = '',
}: {
  children: ReactNode;
  pad?: boolean;
  className?: string;
}) {
  return <div className={`card ${pad ? 'pad' : ''} ${className}`}>{children}</div>;
}

/**
 * Шапка карточки: заголовок слева, опциональное описание и произвольные
 * элементы (бейджи, кнопки) справа через `actions`.
 */
export function CardHeader({
  title,
  description,
  actions,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="card-head">
      <h2>{title}</h2>
      {description && <span className="card-desc">{description}</span>}
      {actions && (
        <>
          <span className="grow" />
          {actions}
        </>
      )}
    </div>
  );
}

export function CardBody({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`card-body ${className}`}>{children}</div>;
}
