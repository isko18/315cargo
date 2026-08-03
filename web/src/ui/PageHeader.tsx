import type { ReactNode } from 'react';

export default function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div className="cluster" style={{ alignItems: 'flex-start' }}>
        <div className="grow">
          <h1>{title}</h1>
          {subtitle && <div className="sub">{subtitle}</div>}
        </div>
        {actions}
      </div>
    </div>
  );
}
