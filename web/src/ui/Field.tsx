import { createContext, forwardRef, useContext, useId, useMemo } from 'react';
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react';
import { IconAlert } from '../components/Icons';

/**
 * Связка «лейбл ↔ контрол» раздаётся через контекст, а не клонированием
 * children: `Input` с иконкой или суффиксом отдаёт обёртку, и клон повесил бы
 * id на div. Контрол внутри `Field` сам забирает id, aria-describedby и
 * aria-invalid — поэтому подпись кликабельна, а ошибка зачитывается вслух.
 */
type FieldCtx = { id: string; describedBy?: string; invalid: boolean };

const FieldContext = createContext<FieldCtx | null>(null);

/** Для сторонних контролов (ClientSearch и т.п.), живущих внутри Field. */
export function useFieldControl() {
  return useContext(FieldContext);
}

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
  const auto = useId();
  const id = htmlFor ?? `f${auto}`;
  const hintId = `${id}-hint`;
  const hasHint = Boolean(error || helper);

  const ctx = useMemo<FieldCtx>(
    () => ({ id, describedBy: hasHint ? hintId : undefined, invalid: Boolean(error) }),
    [id, hintId, hasHint, error],
  );

  return (
    <FieldContext.Provider value={ctx}>
      <div className={`field ${className}`} style={style}>
        {label && (
          <label htmlFor={id}>
            {label}
            {required && <span className="req"> *</span>}
          </label>
        )}
        {children}
        {error ? (
          <div className="field-error" id={hintId}>
            <IconAlert size={13} />
            {error}
          </div>
        ) : helper ? (
          <div className="helper" id={hintId}>
            {helper}
          </div>
        ) : null}
      </div>
    </FieldContext.Provider>
  );
}

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  icon?: ReactNode;
  suffix?: ReactNode;
  invalid?: boolean;
}

/** Инпут с опциональной иконкой слева или суффиксом-единицей справа. */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { icon, suffix, invalid, className = '', id, ...rest },
  ref,
) {
  const field = useContext(FieldContext);
  const isInvalid = invalid ?? field?.invalid ?? false;
  const el = (
    <input
      ref={ref}
      id={id ?? field?.id}
      aria-describedby={rest['aria-describedby'] ?? field?.describedBy}
      aria-invalid={isInvalid || undefined}
      className={`${isInvalid ? 'invalid' : ''} ${className}`.trim()}
      {...rest}
    />
  );
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
  { invalid, className = '', id, children, ...rest },
  ref,
) {
  const field = useContext(FieldContext);
  const isInvalid = invalid ?? field?.invalid ?? false;
  return (
    <select
      ref={ref}
      id={id ?? field?.id}
      aria-describedby={rest['aria-describedby'] ?? field?.describedBy}
      aria-invalid={isInvalid || undefined}
      className={`${isInvalid ? 'invalid' : ''} ${className}`.trim()}
      {...rest}
    >
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
