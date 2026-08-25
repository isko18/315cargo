import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ToastProvider, useToast } from './Toast';

function Trigger() {
  const toast = useToast();
  return (
    <>
      <button onClick={() => toast.success('Готово', 'TRACK-1')}>ok</button>
      <button onClick={() => toast.error('Ошибка')}>fail</button>
    </>
  );
}

function setup() {
  return render(
    <ToastProvider>
      <Trigger />
    </ToastProvider>,
  );
}

describe('ToastProvider', () => {
  it('показывает тост с заголовком и описанием', async () => {
    setup();
    await userEvent.click(screen.getByText('ok'));
    expect(screen.getByText('Готово')).toBeInTheDocument();
    expect(screen.getByText('TRACK-1')).toBeInTheDocument();
  });

  it('область уведомлений — живая (aria-live), чтобы её зачитал скринридер', async () => {
    setup();
    await userEvent.click(screen.getByText('ok'));
    const region = screen.getByRole('region', { name: 'Уведомления' });
    expect(region).toHaveAttribute('aria-live', 'polite');
    expect(region).toContainElement(screen.getByText('Готово'));
  });

  it('закрывается по кнопке', async () => {
    setup();
    await userEvent.click(screen.getByText('fail'));
    expect(screen.getByText('Ошибка')).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText('Закрыть уведомление'));
    expect(screen.queryByText('Ошибка')).not.toBeInTheDocument();
  });

  it('копит несколько уведомлений', async () => {
    setup();
    await userEvent.click(screen.getByText('ok'));
    await userEvent.click(screen.getByText('fail'));
    expect(screen.getByText('Готово')).toBeInTheDocument();
    expect(screen.getByText('Ошибка')).toBeInTheDocument();
  });
});
