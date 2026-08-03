import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { IconClose } from '../components/Icons';

/**
 * Модальное окно для создания/редактирования. Закрывается по Esc, клику вне
 * панели и крестику. Блокирует скролл фона и переносит фокус на первое поле.
 */
export default function Modal({
  title,
  description,
  onClose,
  footer,
  size = 'md',
  children,
}: {
  title: ReactNode;
  description?: ReactNode;
  onClose: () => void;
  footer?: ReactNode;
  size?: 'md' | 'sm';
  children: ReactNode;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  // Монтирование: блокируем скролл фона и один раз фокусируем первое поле.
  // ВАЖНО: без зависимости от onClose — иначе эффект перезапускается на каждый
  // рендер (родитель передаёт новый onClose) и крадёт фокус при каждом вводе.
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const first = panelRef.current?.querySelector<HTMLElement>(
      'input, select, textarea, button:not(.x)',
    );
    first?.focus();
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  // Закрытие по Esc — отдельным эффектом с актуальным onClose.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="modal-overlay" onMouseDown={onClose}>
      <div
        ref={panelRef}
        className={`modal ${size === 'sm' ? 'sm' : ''}`}
        role="dialog"
        aria-modal="true"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <div className="grow">
            <h2>{title}</h2>
            {description && <div className="sub">{description}</div>}
          </div>
          <button type="button" className="x" onClick={onClose} aria-label="Закрыть">
            <IconClose size={20} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}
