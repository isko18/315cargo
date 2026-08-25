import { useEffect, useRef } from 'react';

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Куда ставить фокус при открытии. Крестик и другие кнопки закрытия помечены
 * `data-dialog-dismiss` и исключены: открывать диалог с фокусом на «Закрыть»
 * — значит заставлять пользователя протабать всю форму заново.
 */
const AUTOFOCUS = FOCUSABLE.split(', ')
  .map((sel) => `${sel}:not([data-dialog-dismiss])`)
  .join(', ');

// Скролл фона блокируют и модалка, и дровер — считаем вложенность, иначе
// закрытие верхнего слоя разблокирует страницу под ещё открытым нижним.
let lockCount = 0;
let savedOverflow = '';

function lockScroll() {
  if (lockCount === 0) {
    savedOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
  }
  lockCount += 1;
}

function unlockScroll() {
  lockCount = Math.max(0, lockCount - 1);
  if (lockCount === 0) document.body.style.overflow = savedOverflow;
}

export interface DialogOptions {
  onClose: () => void;
  /** Блокировать скролл фона (по умолчанию — да). */
  lock?: boolean;
  /** Фокусировать первый элемент при открытии (по умолчанию — да). */
  autoFocus?: boolean;
}

/**
 * Поведение модального слоя: Esc, ловушка фокуса по Tab/Shift+Tab, возврат
 * фокуса на элемент-инициатор при закрытии и блокировка скролла фона.
 *
 * Возвращает ref, который нужно повесить на панель диалога.
 */
export function useDialog<T extends HTMLElement>({ onClose, lock = true, autoFocus = true }: DialogOptions) {
  const ref = useRef<T>(null);
  // Держим onClose в ref: иначе эффект перезапускается на каждый рендер
  // родителя и крадёт фокус при каждом нажатии клавиши в поле.
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const panel = ref.current;
    const opener = document.activeElement as HTMLElement | null;
    if (lock) lockScroll();

    if (autoFocus) {
      const first =
        panel?.querySelector<HTMLElement>(AUTOFOCUS) ?? panel?.querySelector<HTMLElement>(FOCUSABLE);
      (first ?? panel)?.focus();
    }

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.stopPropagation();
        closeRef.current();
        return;
      }
      if (e.key !== 'Tab' || !panel) return;
      const items = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (el) => el.offsetParent !== null || el === document.activeElement,
      );
      if (items.length === 0) {
        e.preventDefault();
        panel.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && (active === first || active === panel)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener('keydown', onKeyDown, true);
    return () => {
      document.removeEventListener('keydown', onKeyDown, true);
      if (lock) unlockScroll();
      // Возврат фокуса туда, откуда диалог открыли — иначе Tab начинается сначала.
      if (opener && document.contains(opener)) opener.focus();
    };
  }, [lock, autoFocus]);

  return ref;
}
