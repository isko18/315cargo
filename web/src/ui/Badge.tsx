import type { ReactNode } from 'react';
import type { Tone } from '../status';

// Семантические варианты (готовые классы) + тональные (tone-*).
type Variant = Tone | 'ok' | 'warn' | 'plain';

const SEMANTIC = new Set(['ok', 'warn', 'plain']);

export default function Badge({
  variant = 'plain',
  dot = false,
  className = '',
  children,
}: {
  variant?: Variant;
  dot?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const cls = SEMANTIC.has(variant) ? variant : `tone-${variant}`;
  return (
    <span className={`badge ${cls} ${className}`}>
      {dot && <span className="dot" />}
      {children}
    </span>
  );
}
