import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, cleanup } from '@testing-library/react';
import { useBarcodeScanner } from './useBarcodeScanner';

function Harness({ onScan }: { onScan: (code: string) => void }) {
  useBarcodeScanner(onScan);
  return null;
}

function key(k: string) {
  window.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true }));
}

describe('useBarcodeScanner', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('быстрая серия + Enter распознаётся как скан', () => {
    let now = 0;
    vi.spyOn(performance, 'now').mockImplementation(() => now);
    const onScan = vi.fn();
    render(<Harness onScan={onScan} />);

    for (const ch of 'ABC12345') {
      now += 10; // быстро — как сканер
      key(ch);
    }
    now += 10;
    key('Enter');

    expect(onScan).toHaveBeenCalledOnce();
    expect(onScan).toHaveBeenCalledWith('ABC12345');
  });

  it('медленный человеческий ввод не считается сканом', () => {
    let now = 0;
    vi.spyOn(performance, 'now').mockImplementation(() => now);
    const onScan = vi.fn();
    render(<Harness onScan={onScan} />);

    for (const ch of 'ABC123') {
      now += 150; // медленно — человек
      key(ch);
    }
    now += 150;
    key('Enter');

    expect(onScan).not.toHaveBeenCalled();
  });

  it('слишком короткая серия игнорируется', () => {
    let now = 0;
    vi.spyOn(performance, 'now').mockImplementation(() => now);
    const onScan = vi.fn();
    render(<Harness onScan={onScan} />);

    now += 10;
    key('A');
    now += 10;
    key('Enter');

    expect(onScan).not.toHaveBeenCalled();
  });
});
