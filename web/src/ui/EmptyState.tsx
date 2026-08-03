import type { ReactNode } from 'react';

export default function EmptyState({
  icon,
  title,
  description,
  action,
  compact = false,
}: {
  icon?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  compact?: boolean;
}) {
  return (
    <div className="empty" style={compact ? { padding: 28 } : undefined}>
      {icon && <div className="empty-ico">{icon}</div>}
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {action && <div className="mt-md">{action}</div>}
    </div>
  );
}
