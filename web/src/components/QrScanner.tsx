import { useEffect, useRef } from 'react';
import { Html5Qrcode } from 'html5-qrcode';

/// Камера-сканер QR. Наводишь на QR клиента → onResult(client_code).
/// Требует HTTPS (или localhost) — иначе браузер не даст доступ к камере.
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

  useEffect(() => {
    const scanner = new Html5Qrcode(elId);
    scannerRef.current = scanner;

    scanner
      .start(
        { facingMode: 'environment' },
        { fps: 10, qrbox: 240 },
        (decoded) => {
          if (handledRef.current) return;
          handledRef.current = true;
          scanner.stop().catch(() => {}).finally(() => onResult(decoded.trim()));
        },
        () => {}, // ошибки распознавания кадра — игнор
      )
      .catch((e) => {
        alert('Нет доступа к камере: ' + e);
        onClose();
      });

    return () => {
      scannerRef.current
        ?.stop()
        .catch(() => {})
        .finally(() => scannerRef.current?.clear());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="qr-overlay" onClick={onClose}>
      <div className="qr-modal" onClick={(e) => e.stopPropagation()}>
        <h2>Наведите на QR клиента</h2>
        <div id={elId} style={{ width: '100%' }} />
        <button className="ghost" onClick={onClose} style={{ marginTop: 12, width: '100%' }}>
          Закрыть
        </button>
      </div>
    </div>
  );
}
