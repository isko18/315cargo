import { useState } from 'react';
import { useI18n } from '../i18n';
import CopyBox from './CopyBox';
import { Button } from '../ui';

/**
 * Ссылка-приглашение карго: клиент переходит по ней и попадает в приложение
 * с уже выбранным карго. QR приходит с бэкенда готовым data-URI — карго
 * раздают его офлайн (визитки, чаты, склад).
 *
 * Раздавать нужно именно invite_url: у кого приложение стоит — откроется
 * приложение, у кого нет — страница с кнопкой в Play, куда уже подшит
 * referrer. Прямая ссылка на Play второй случай закрывает так же, а первый
 * ломает (вместо приложения откроется магазин), поэтому она спрятана.
 */
export default function InviteLink({
  url,
  qr,
  playUrl,
}: {
  url: string;
  qr?: string | null;
  /** Прямая ссылка на Play с Install Referrer — запасной вариант. */
  playUrl?: string | null;
}) {
  const { t } = useI18n();
  const [showPlay, setShowPlay] = useState(false);

  return (
    <div className="invite">
      {qr && <img className="invite-qr" src={qr} alt={t('invite.qrAlt')} width={132} height={132} />}
      <div className="invite-body">
        <CopyBox text={url} />
        {qr && (
          <a className="invite-dl mt-sm" href={qr} download="cargo-invite-qr.png">
            {t('invite.download')}
          </a>
        )}
        <p className="helper mt-sm">{t('invite.hint')}</p>

        {playUrl && (
          <div className="mt-md">
            <Button
              type="button"
              variant="subtle"
              size="sm"
              onClick={() => setShowPlay((v) => !v)}
              aria-expanded={showPlay}
            >
              {t('invite.playToggle')}
            </Button>
            {showPlay && (
              <div className="mt-sm">
                <CopyBox text={playUrl} />
                <p className="helper mt-sm">{t('invite.playHint')}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
