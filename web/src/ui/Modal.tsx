import { useId } from 'react';
import type { ReactNode } from 'react';
import { IconClose } from '../components/Icons';
import { useDialog } from './useDialog';

/**
 * Модальное окно для создания/редактирования. Закрывается по Esc, клику вне
 * панели и крестику. Фокус заперт внутри окна и возвращается на элемент,
 * которым его открыли (см. useDialog).
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
  const panelRef = useDialog<HTMLDivElement>({ onClose });
  const titleId = useId();
  const descId = useId();

  return (
    <div className="modal-overlay" onMouseDown={onClose}>
      <div
        ref={panelRef}
        className={`modal ${size === 'sm' ? 'sm' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
        tabIndex={-1}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <div className="grow">
            <h2 id={titleId}>{title}</h2>
            {description && (
              <div className="sub" id={descId}>
                {description}
              </div>
            )}
          </div>
          <button type="button" className="x" data-dialog-dismiss onClick={onClose} aria-label="Закрыть">
            <IconClose size={20} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}
