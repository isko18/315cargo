import type { ReactNode } from 'react';
import type { Tone } from '../status';

export function StatGrid({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`stat-grid ${className}`}>{children}</div>;
}

export function Stat({
  icon,
  tone,
  label,
  value,
  hint,
}: {
  icon?: ReactNode;
  tone?: Tone;
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <div className={`stat ${tone ? `tone-${tone}` : ''}`}>
      <div className="stat-top">
        {icon && <span className="stat-ico">{icon}</span>}
        <span className="stat-label">{label}</span>
      </div>
      <div className="stat-value">{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}
