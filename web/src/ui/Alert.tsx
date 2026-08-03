import type { ReactNode } from 'react';
import { IconAlert, IconCheck } from '../components/Icons';

type Variant = 'error' | 'success' | 'info';

const ICON: Record<Variant, ReactNode> = {
  error: <IconAlert size={18} />,
  success: <IconCheck size={18} />,
  info: <IconAlert size={18} />,
};

export default function Alert({
  variant = 'info',
  icon,
  className = '',
  children,
}: {
  variant?: Variant;
  icon?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={`alert ${variant} ${className}`} role={variant === 'error' ? 'alert' : undefined}>
      {icon ?? ICON[variant]}
      <span>{children}</span>
    </div>
  );
}
