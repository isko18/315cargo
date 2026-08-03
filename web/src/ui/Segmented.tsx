export interface SegmentedOption<T extends string> {
  value: T;
  label: React.ReactNode;
}

/** Сегментированный переключатель (фильтр периода и т.п.). */
export default function Segmented<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: SegmentedOption<T>[];
  value: T | null;
  onChange: (value: T) => void;
  ariaLabel?: string;
}) {
  return (
    <div className="seg" role="group" aria-label={ariaLabel}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          className={value === o.value ? 'active' : ''}
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
