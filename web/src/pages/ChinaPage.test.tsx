import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const post = vi.fn();
vi.mock('../api', () => ({
  post: (...args: unknown[]) => post(...args),
  get: vi.fn(async () => []),
  getRole: () => ({ is_china_staff: true, is_superuser: false, is_cargo_admin: false }),
  ApiError: class extends Error {},
}));

import ChinaPage from './ChinaPage';
import { I18nProvider } from '../i18n';
import { ToastProvider } from '../ui/Toast';

function renderPage() {
  return render(
    <I18nProvider>
      <ToastProvider>
        <ChinaPage />
      </ToastProvider>
    </I18nProvider>,
  );
}

const reply = (track: string, result = 'created_manual') => ({
  result,
  parcel: {
    id: Math.floor(Math.random() * 1e6),
    track_number: track,
    status: 'arrived_china_warehouse',
    status_display_name: 'На складе в Китае',
    client_code: null,
    user: null,
  },
});

/** Скан штрих-сканером: быстрая серия символов + Enter. */
async function scanBarcode(code: string) {
  let now = 0;
  vi.spyOn(performance, 'now').mockImplementation(() => (now += 10));
  for (const ch of code) {
    window.dispatchEvent(new KeyboardEvent('keydown', { key: ch, bubbles: true, cancelable: true }));
  }
  window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
}

describe('ChinaPage — приёмка на складе', () => {
  beforeEach(() => post.mockReset());
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('не теряет сканы, сделанные пока идёт запрос', async () => {
    // Ровно та ситуация, из-за которой коробки пропадали: оператор сканирует
    // подряд, а сеть отвечает медленно.
    // Каждый запрос отвечает не мгновенно — как реальная сеть.
    post.mockImplementation(
      (_url: string, body: any) =>
        new Promise((res) => setTimeout(() => res(reply(body.track_number)), 15)),
    );

    renderPage();
    await scanBarcode('AAA111');
    await scanBarcode('BBB222');
    await scanBarcode('CCC333');

    // Все три видны сразу, ещё до ответов сервера — раньше второй и третий
    // молча выбрасывались.
    await waitFor(() => expect(screen.getByText('AAA111')).toBeInTheDocument());
    expect(screen.getByText('BBB222')).toBeInTheDocument();
    expect(screen.getByText('CCC333')).toBeInTheDocument();

    await waitFor(() => expect(post).toHaveBeenCalledTimes(3), { timeout: 3000 });

    const sent = post.mock.calls.map((c) => (c[1] as any).track_number);
    expect(sent).toEqual(['AAA111', 'BBB222', 'CCC333']);
  });

  it('отправляет по одному, сохраняя порядок сканирования', async () => {
    const order: string[] = [];
    post.mockImplementation(async (_url: string, body: any) => {
      order.push(`start:${body.track_number}`);
      await new Promise((r) => setTimeout(r, 5));
      order.push(`end:${body.track_number}`);
      return reply(body.track_number);
    });

    renderPage();
    await scanBarcode('AAA111');
    await scanBarcode('BBB222');

    await waitFor(() => expect(order).toHaveLength(4), { timeout: 3000 });
    // Второй запрос не должен стартовать до завершения первого.
    expect(order).toEqual(['start:AAA111', 'end:AAA111', 'start:BBB222', 'end:BBB222']);
  });

  it('дубль от сканера не отправляется дважды', async () => {
    post.mockImplementation(
      (_url: string, body: any) => new Promise((res) => setTimeout(() => res(reply(body.track_number)), 20)),
    );

    renderPage();
    await scanBarcode('AAA111');
    await scanBarcode('AAA111');

    await waitFor(() => expect(post).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 60));
    expect(post).toHaveBeenCalledTimes(1);
  });

  it('упавший скан помечается и повторяется без пересканирования', async () => {
    post.mockRejectedValueOnce(Object.assign(new Error('нет связи'), { message: 'нет связи' }));
    renderPage();

    await scanBarcode('AAA111');
    const retry = await screen.findByRole('button', { name: 'Повторить' });

    post.mockResolvedValueOnce(reply('AAA111'));
    await userEvent.click(retry);

    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect((post.mock.calls[1][1] as any).track_number).toBe('AAA111');
  });
});
