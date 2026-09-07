import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const post = vi.fn();
vi.mock('../api', () => ({
  post: (...args: unknown[]) => post(...args),
  get: vi.fn(async () => []),
  getRole: () => ({ is_superuser: false, is_cargo_admin: false, is_china_staff: false }),
  ApiError: class extends Error {},
}));
vi.mock('../pickupContext', () => ({
  usePickup: () => ({ points: [], activeId: null, setActiveId: vi.fn(), reload: vi.fn() }),
}));

import ScanPage from './ScanPage';
import { I18nProvider } from '../i18n';
import { ToastProvider } from '../ui/Toast';

function renderPage() {
  return render(
    <I18nProvider>
      <ToastProvider>
        <ScanPage />
      </ToastProvider>
    </I18nProvider>,
  );
}

const reply = (track: string) => ({
  result: 'updated',
  parcel: {
    id: Math.floor(Math.random() * 1e6),
    track_number: track,
    status: 'at_pickup_point',
    status_display_name: 'В ПВЗ',
    client_code: null,
    user: null,
    weight: null,
    delivery_price: null,
  },
});

async function scanBarcode(code: string) {
  let now = 0;
  vi.spyOn(performance, 'now').mockImplementation(() => (now += 10));
  for (const ch of code) {
    window.dispatchEvent(new KeyboardEvent('keydown', { key: ch, bubbles: true, cancelable: true }));
  }
  window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
}

describe('ScanPage — приём в ПВЗ', () => {
  beforeEach(() => post.mockReset());
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('не теряет сканы, сделанные пока идёт запрос', async () => {
    post.mockImplementation(
      (_url: string, body: any) =>
        new Promise((res) => setTimeout(() => res(reply(body.track_number)), 15)),
    );

    renderPage();
    await scanBarcode('AAA111');
    await scanBarcode('BBB222');
    await scanBarcode('CCC333');

    await waitFor(() => expect(screen.getByText('AAA111')).toBeInTheDocument());
    expect(screen.getByText('BBB222')).toBeInTheDocument();
    expect(screen.getByText('CCC333')).toBeInTheDocument();

    await waitFor(() => expect(post).toHaveBeenCalledTimes(3), { timeout: 3000 });
    expect(post.mock.calls.map((c) => (c[1] as any).track_number)).toEqual([
      'AAA111',
      'BBB222',
      'CCC333',
    ]);
  });

  it('вес относится к своей коробке, а не к последней введённой', async () => {
    // Вес фиксируется на момент скана: пока очередь разгребается, оператор
    // успевает поменять поле, и вес не должен «переехать» на другую коробку.
    post.mockImplementation(
      (_url: string, body: any) =>
        new Promise((res) => setTimeout(() => res(reply(body.track_number)), 15)),
    );

    renderPage();
    const weightInput = screen.getByPlaceholderText('напр. 2.5');
    await userEvent.type(weightInput, '3.5');
    await scanBarcode('AAA111');
    await scanBarcode('BBB222');

    await waitFor(() => expect(post).toHaveBeenCalledTimes(2), { timeout: 3000 });
    expect((post.mock.calls[0][1] as any).weight).toBe('3.5');
    // Поле очищается после скана — второй коробке вес не приписывается.
    expect((post.mock.calls[1][1] as any).weight).toBeUndefined();
  });

  it('упавший скан можно повторить из строки', async () => {
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
