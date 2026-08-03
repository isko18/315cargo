import type { ButtonHTMLAttributes, ReactNode } from 'react';

type Variant = 'primary' | 'secondary' | 'subtle' | 'danger';
type Size = 'md' | 'sm';

const VARIANT_CLASS: Record<Variant, string> = {
  primary: '',
  secondary: 'ghost',
  subtle: 'subtle',
  danger: 'danger',
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
  block?: boolean;
}

/**
 * Единая кнопка приложения. Инкапсулирует иерархию (primary/secondary/subtle/
 * danger), размеры, состояние загрузки (спиннер + блокировка) и иконку.
 */
export default function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  icon,
  block = false,
  className = '',
  disabled,
  children,
  ...rest
}: ButtonProps) {
  const cls = [
    VARIANT_CLASS[variant],
    size === 'sm' ? 'sm' : '',
    block ? 'block' : '',
    !children ? 'icon-only' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button className={cls} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading ? <span className="spinner" /> : icon}
      {children}
    </button>
  );
}
