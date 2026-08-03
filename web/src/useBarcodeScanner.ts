import { useEffect, useRef } from 'react';

/**
 * Глобальный перехват штрих-сканера (как на кассе в магазине).
 *
 * Сканер эмулирует клавиатуру: очень быстро «печатает» код и шлёт Enter.
 * Хук ловит такие быстрые серии символов на уровне документа — код
 * подхватывается независимо от того, где фокус (не нужно кликать в поле).
 *
 * Ручной ввод человека медленный (паузы > FAST_MS), поэтому он НЕ считается
 * сканом и не мешает обычному набору в полях.
 */
export function useBarcodeScanner(onScan: (code: string) => void, enabled = true) {
  const cb = useRef(onScan);
  cb.current = onScan;

  useEffect(() => {
    if (!enabled) return;

    const RESET_MS = 200; // пауза, начинающая новую серию
    const FAST_MS = 50; // максимальный интервал между «нажатиями» сканера
    const MIN_LEN = 3; // минимум символов, чтобы считать сканом

    let buf = '';
    let last = 0;
    let fast = true;

    const onKey = (e: KeyboardEvent) => {
      const now = performance.now();

      if (e.key === 'Enter') {
        const looksLikeScan = buf.length >= MIN_LEN && fast;
        const code = buf;
        buf = '';
        if (looksLikeScan) {
          // Не даём Enter/символам «утечь» в сфокусированное поле или форму.
          e.preventDefault();
          e.stopPropagation();
          cb.current(code.trim());
        }
        return;
      }

      // Только печатные одиночные символы, без модификаторов.
      if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
        const gap = now - last;
        if (gap > RESET_MS) {
          buf = '';
          fast = true;
        } else if (gap > FAST_MS) {
          fast = false; // слишком медленно для сканера — это человек
        }
        buf += e.key;
        last = now;
      }
    };

    // Capture-фаза: перехватываем раньше React-обработчиков полей.
    window.addEventListener('keydown', onKey, true);
    return () => window.removeEventListener('keydown', onKey, true);
  }, [enabled]);
}
