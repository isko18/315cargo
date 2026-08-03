import { useEffect, useRef, useState } from 'react';

/**
 * Инлайн-ввод веса прямо в строке таблицы (приём и выдача).
 * Сохраняет по Enter/blur; цена доставки пересчитывается на бэкенде.
 */
export default function WeightInline({
  value,
  onSave,
  disabled,
  autoFocus,
}: {
  value: string | null;
  onSave: (weight: string) => Promise<void>;
  disabled?: boolean;
  autoFocus?: boolean;
}) {
  const [v, setV] = useState(value ?? '');
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState(false);
  const ref = useRef<HTMLInputElement>(null);

  // Внешнее обновление (перезагрузка списка) синхронизирует поле.
  useEffect(() => {
    setV(value ?? '');
  }, [value]);

  async function commit() {
    const next = v.trim();
    if (next === (value ?? '').trim()) return; // без изменений — не дёргаем сеть
    setBusy(true);
    setOk(false);
    try {
      await onSave(next);
      setOk(true);
      setTimeout(() => setOk(false), 1200);
    } catch {
      // Ошибку показывает родитель (Alert); поле остаётся с введённым значением.
      setV(value ?? '');
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className={`w-inline ${ok ? 'saved' : ''}`}>
      <input
        ref={ref}
        type="number"
        min="0"
        step="0.001"
        inputMode="decimal"
        value={v}
        disabled={disabled || busy}
        autoFocus={autoFocus}
        onChange={(e) => setV(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
        }}
        onBlur={commit}
        onClick={(e) => e.stopPropagation()}
        placeholder="—"
        aria-label="кг"
      />
      <span className="w-suffix">кг</span>
    </span>
  );
}
