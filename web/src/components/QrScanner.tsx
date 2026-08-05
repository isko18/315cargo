import { useEffect, useRef, useState } from 'react';
import {
  Html5Qrcode,
  Html5QrcodeScannerState,
  Html5QrcodeSupportedFormats,
  type Html5QrcodeCameraScanConfig,
} from 'html5-qrcode';

/// Камера-сканер QR. Наводишь на QR клиента → onResult(client_code).
/// Требует HTTPS (или localhost) — иначе браузер не даст доступ к камере.

// Понятное объяснение вместо «[object Object]» из html5-qrcode.
function describe(e: unknown): string {
  const name = (e as DOMException)?.name ?? '';
  const raw = typeof e === 'string' ? e : ((e as Error)?.message ?? String(e ?? ''));
  if (name === 'NotAllowedError' || /permission|denied|NotAllowed/i.test(raw))
    return 'Доступ к камере запрещён. Разрешите камеру для сайта в настройках браузера (значок замка в адресной строке) и попробуйте снова.';
  if (name === 'NotFoundError' || name === 'OverconstrainedError' || /NotFound|no camera|OverConstrained/i.test(raw))
    return 'Камера не найдена. Подключите камеру или откройте страницу на телефоне.';
  if (name === 'NotReadableError' || /NotReadable|in use|could not start/i.test(raw))
    return 'Камера занята другим приложением или вкладкой. Закройте их и попробуйте снова.';
  return raw || 'Не удалось запустить камеру.';
}

// qrbox не должен быть больше кадра — иначе html5-qrcode падает на узких экранах.
const scanConfig: Html5QrcodeCameraScanConfig = {
  fps: 10,
  qrbox: (w: number, h: number) => {
    const side = Math.max(120, Math.floor(Math.min(w, h) * 0.75));
    return { width: side, height: side };
  },
};

export default function QrScanner({
  onResult,
  onClose,
}: {
  onResult: (text: string) => void;
  onClose: () => void;
}) {
  const elId = 'qr-reader';
  const scannerRef = useRef<Html5Qrcode | null>(null);
  const handledRef = useRef(false);
  const [error, setError] = useState('');
  const [starting, setStarting] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function stop() {
      const s = scannerRef.current;
      scannerRef.current = null;
      if (!s) return;
      try {
        const st = s.getState();
        if (st === Html5QrcodeScannerState.SCANNING || st === Html5QrcodeScannerState.PAUSED) {
          await s.stop();
        }
      } catch {
        /* уже остановлен */
      }
      try {
        s.clear();
      } catch {
        /* элемент уже размонтирован */
      }
    }

    async function boot() {
      if (!window.isSecureContext) {
        setError('Камера работает только по HTTPS. Откройте сайт по https://');
        setStarting(false);
        return;
      }
      if (!navigator.mediaDevices?.getUserMedia) {
        setError('Браузер не поддерживает доступ к камере. Обновите браузер или откройте сайт в Chrome/Safari.');
        setStarting(false);
        return;
      }

      const onDecoded = (decoded: string) => {
        if (handledRef.current) return;
        handledRef.current = true;
        stop().finally(() => onResult(decoded.trim()));
      };

      const scanner = new Html5Qrcode(elId, {
        verbose: false,
        formatsToSupport: [Html5QrcodeSupportedFormats.QR_CODE],
      });
      scannerRef.current = scanner;

      try {
        await scanner.start({ facingMode: 'environment' }, scanConfig, onDecoded, undefined);
      } catch (e1) {
        // Не всякое устройство понимает facingMode — пробуем конкретную камеру.
        try {
          const cams = await Html5Qrcode.getCameras();
          if (!cams.length) throw e1;
          const back = cams.find((c) => /back|rear|environment|задн/i.test(c.label)) ?? cams[cams.length - 1];
          await scanner.start(back.id, scanConfig, onDecoded, undefined);
        } catch (e2) {
          if (!cancelled) {
            setError(describe(e2 ?? e1));
            setStarting(false);
          }
          scannerRef.current = null;
          return;
        }
      }

      if (cancelled) {
        // StrictMode/быстрое закрытие: камеру, поднятую после размонтирования, гасим.
        await stop();
        return;
      }
      setStarting(false);
    }

    boot();

    return () => {
      cancelled = true;
      stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="qr-overlay" onClick={onClose}>
      <div className="qr-modal" onClick={(e) => e.stopPropagation()}>
        <h2>Наведите на QR клиента</h2>
        <div id={elId} style={{ width: '100%', minHeight: error ? 0 : 200 }} />
        {starting && !error && (
          <p className="muted" style={{ textAlign: 'center', marginTop: 8 }}>
            Запуск камеры…
          </p>
        )}
        {error && (
          <div className="alert error" style={{ marginTop: 12 }}>
            {error}
          </div>
        )}
        <button className="ghost" onClick={onClose} style={{ marginTop: 12, width: '100%' }}>
          Закрыть
        </button>
      </div>
    </div>
  );
}
