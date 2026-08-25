import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { IconAlert, IconCheckCircle, IconClose, IconInfo } from '../components/Icons';

/**
 * Всплывающие уведомления об итоге операции. Нужны там, где оператор смотрит
 * на сканер, а не на форму: инлайн-алерт в такой момент легко пропустить.
 *
 * Область объявлена как aria-live="polite" — скринридер зачитает текст, не
 * прерывая текущую фразу. Ошибки не гасим по таймеру слишком быстро.
 */
export type ToastVariant = 'success' | 'error' | 'info';

export type ToastInput = {
  variant?: ToastVariant;
  title: ReactNode;
  description?: ReactNode;
  /** Мс до автозакрытия. 0 — не закрывать автоматически. */
  duration?: number;
};

type Toast = ToastInput & { id: number; variant: ToastVariant };

const DEFAULT_DURATION: Record<ToastVariant, number> = {
  success: 3500,
  info: 4500,
  error: 8000,
};

const MAX_VISIBLE = 4;

const ICON: Record<ToastVariant, ReactNode> = {
  success: <IconCheckCircle size={18} />,
  error: <IconAlert size={18} />,
  info: <IconInfo size={18} />,
};

type Ctx = {
  show: (t: ToastInput) => number;
  success: (title: ReactNode, description?: ReactNode) => number;
  error: (title: ReactNode, description?: ReactNode) => number;
  info: (title: ReactNode, description?: ReactNode) => number;
  dismiss: (id: number) => void;
};

const noop = () => 0;
const ToastCtx = createContext<Ctx>({
  show: noop,
  success: noop,
  error: noop,
  info: noop,
  dismiss: () => {},
});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seq = useRef(0);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
    setToasts((list) => list.filter((t) => t.id !== id));
  }, []);

  const show = useCallback(
    (input: ToastInput) => {
      const variant = input.variant ?? 'info';
      const id = ++seq.current;
      const toast: Toast = { ...input, variant, id };
      setToasts((list) => [...list, toast].slice(-MAX_VISIBLE));
      const duration = input.duration ?? DEFAULT_DURATION[variant];
      if (duration > 0) {
        timers.current.set(
          id,
          setTimeout(() => dismiss(id), duration),
        );
      }
      return id;
    },
    [dismiss],
  );

  // Чистим таймеры при размонтировании провайдера (тесты, HMR).
  useEffect(() => {
    const map = timers.current;
    return () => {
      map.forEach(clearTimeout);
      map.clear();
    };
  }, []);

  const value = useMemo<Ctx>(
    () => ({
      show,
      dismiss,
      success: (title, description) => show({ variant: 'success', title, description }),
      error: (title, description) => show({ variant: 'error', title, description }),
      info: (title, description) => show({ variant: 'info', title, description }),
    }),
    [show, dismiss],
  );

  return (
    <ToastCtx.Provider value={value}>
      {children}
      <div className="toast-viewport" role="region" aria-live="polite" aria-label="Уведомления">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.variant}`}>
            <span className="toast-ico">{ICON[t.variant]}</span>
            <div className="toast-body">
              <div className="toast-title">{t.title}</div>
              {t.description && <div className="toast-desc">{t.description}</div>}
            </div>
            <button
              type="button"
              className="toast-x"
              onClick={() => dismiss(t.id)}
              aria-label="Закрыть уведомление"
            >
              <IconClose size={16} />
            </button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  return useContext(ToastCtx);
}
