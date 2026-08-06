import { useState } from 'react';
import { IconCheck, IconPin } from './Icons';
import { useI18n } from '../i18n';
import { Button } from '../ui';

/** Строка с кнопкой «Копировать»: ссылка-приглашение, адрес для PDD и т.п. */
export default function CopyBox({
  text,
  label,
  empty,
}: {
  text: string;
  /** Подпись кнопки; по умолчанию — «Копировать». */
  label?: string;
  /** Что показать вместо текста, если копировать нечего. */
  empty?: string;
}) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const [id] = useState(() => `copy-${Math.random().toString(36).slice(2, 9)}`);

  async function copy() {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // Буфер недоступен (нет HTTPS/разрешения) — выделяем текст, копирует сам.
      const node = document.getElementById(id);
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
    <div>
      <code id={id} className="invite-url">{text || empty || '—'}</code>
      <div className="cluster gap-sm mt-md">
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={copy}
          disabled={!text}
          icon={copied ? <IconCheck size={16} /> : <IconPin size={16} />}
        >
          {copied ? t('invite.copied') : label ?? t('invite.copy')}
        </Button>
      </div>
    </div>
  );
}
