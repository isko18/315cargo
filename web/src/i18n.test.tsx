import { describe, expect, it, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { I18nProvider, useI18n } from './i18n';

function Probe({ k }: { k: string }) {
  const { t, lang, setLang } = useI18n();
  return (
    <div>
      <span data-testid="val">{t(k)}</span>
      <span data-testid="lang">{lang}</span>
      <button onClick={() => setLang('zh')}>zh</button>
    </div>
  );
}

describe('i18n', () => {
  beforeEach(() => localStorage.clear());

  it('по умолчанию русский', () => {
    render(
      <I18nProvider>
        <Probe k="login.submit" />
      </I18nProvider>,
    );
    expect(screen.getByTestId('lang').textContent).toBe('ru');
    expect(screen.getByTestId('val').textContent).toBe('Войти');
  });

  it('китайский из localStorage', () => {
    localStorage.setItem('lang', 'zh');
    render(
      <I18nProvider>
        <Probe k="china.title" />
      </I18nProvider>,
    );
    expect(screen.getByTestId('val').textContent).toBe('中国仓库');
  });

  it('неизвестный ключ возвращается как есть', () => {
    render(
      <I18nProvider>
        <Probe k="nope.key" />
      </I18nProvider>,
    );
    expect(screen.getByTestId('val').textContent).toBe('nope.key');
  });
});
