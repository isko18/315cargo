import { useI18n } from '../i18n';
import CopyBox from './CopyBox';

/**
 * Ссылка-приглашение карго: клиент переходит по ней и попадает в приложение
 * с уже выбранным карго. QR приходит с бэкенда готовым data-URI — карго
 * раздают его офлайн (визитки, чаты, склад).
 */
export default function InviteLink({ url, qr }: { url: string; qr?: string | null }) {
  const { t } = useI18n();

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
      </div>
    </div>
  );
}
