import { useState } from 'react';
import { IconCheck, IconPin } from './Icons';
import { useI18n } from '../i18n';
import { Button } from '../ui';

/**
 * Ссылка-приглашение карго: клиент переходит по ней и попадает в приложение
 * с уже выбранным карго. QR приходит с бэкенда готовым data-URI — карго
 * раздают его офлайн (визитки, чаты, склад).
 */
export default function InviteLink({ url, qr }: { url: string; qr?: string | null }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // Буфер недоступен (нет HTTPS/разрешения) — выделяем текст, копирует сам.
      const node = document.getElementById('invite-url');
      const sel = window.getSelection();
      if (node && sel) {
        const range = document.createRange();
        range.selectNodeContents(node);
        sel.removeAllRanges();
        sel.addRange(range);
      }
    }
  }

  return (
    <div className="invite">
      {qr && <img className="invite-qr" src={qr} alt={t('invite.qrAlt')} width={132} height={132} />}
      <div className="invite-body">
        <code id="invite-url" className="invite-url">{url}</code>
        <div className="cluster gap-sm mt-md">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={copy}
            icon={copied ? <IconCheck size={16} /> : <IconPin size={16} />}
          >
            {copied ? t('invite.copied') : t('invite.copy')}
          </Button>
          {qr && (
            <a className="invite-dl" href={qr} download="cargo-invite-qr.png">
              {t('invite.download')}
            </a>
          )}
        </div>
        <p className="helper mt-sm">{t('invite.hint')}</p>
      </div>
    </div>
  );
}
