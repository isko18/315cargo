import { forwardRef } from 'react';
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react';
import { IconAlert } from '../components/Icons';

/** Обёртка поля формы: лейбл, признак обязательности, helper или ошибка. */
export function Field({
  label,
  htmlFor,
  required,
  helper,
  error,
  className = '',
  style,
  children,
}: {
  label?: ReactNode;
  htmlFor?: string;
  required?: boolean;
  helper?: ReactNode;
  error?: ReactNode;
  className?: string;
  style?: React.CSSProperties;
  children: ReactNode;
}) {
  return (
    <div className={`field ${className}`} style={style}>
      {label && (
        <label htmlFor={htmlFor}>
          {label}
          {required && <span className="req"> *</span>}
        </label>
      )}
      {children}
      {error ? (
        <div className="field-error">
          <IconAlert size={13} />
          {error}
        </div>
      ) : helper ? (
        <div className="helper">{helper}</div>
      ) : null}
    </div>
  );
}

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  icon?: ReactNode;
  suffix?: ReactNode;
  invalid?: boolean;
}

/** Инпут с опциональной иконкой слева или суффиксом-единицей справа. */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { icon, suffix, invalid, className = '', ...rest },
  ref,
) {
  const el = <input ref={ref} className={`${invalid ? 'invalid' : ''} ${className}`} {...rest} />;
  if (icon) {
    return (
      <div className="input-group">
        {icon}
        {el}
      </div>
    );
  }
  if (suffix) {
    return (
      <div className="suffix">
        {el}
        <span className="unit">{suffix}</span>
      </div>
    );
  }
  return el;
});

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  invalid?: boolean;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { invalid, className = '', children, ...rest },
  ref,
) {
  return (
    <select ref={ref} className={`${invalid ? 'invalid' : ''} ${className}`} {...rest}>
      {children}
    </select>
  );
});

export function Checkbox({
  checked,
  onChange,
  children,
  disabled,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  children: ReactNode;
  disabled?: boolean;
}) {
  return (
    <label className="checkbox">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      {children}
    </label>
  );
}
