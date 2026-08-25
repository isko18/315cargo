import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Modal from './Modal';

function open(onClose = vi.fn()) {
  render(
    <Modal title="Новый ПВЗ" description="заполните поля" onClose={onClose}>
      <input aria-label="Название" />
      <button>Сохранить</button>
    </Modal>,
  );
  return onClose;
}

describe('Modal', () => {
  it('объявлен как модальный диалог со своим заголовком', () => {
    open();
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAccessibleName('Новый ПВЗ');
    expect(dialog).toHaveAccessibleDescription('заполните поля');
  });

  it('закрывается по Esc', async () => {
    const onClose = open();
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalled();
  });

  it('фокус уходит на первый контрол и не выходит за пределы окна по Tab', async () => {
    open();
    const input = screen.getByLabelText('Название');
    expect(input).toHaveFocus();

    // Tab по кругу: последний элемент → первый, наружу фокус не уходит.
    const inside = [input, screen.getByText('Сохранить'), screen.getByLabelText('Закрыть')];
    for (let i = 0; i < inside.length + 1; i += 1) {
      await userEvent.tab();
      expect(inside).toContain(document.activeElement);
    }
  });

  it('возвращает фокус на элемент, которым его открыли', () => {
    const opener = document.createElement('button');
    document.body.appendChild(opener);
    opener.focus();

    const { unmount } = render(
      <Modal title="Окно" onClose={() => {}}>
        <input aria-label="Поле" />
      </Modal>,
    );
    expect(screen.getByLabelText('Поле')).toHaveFocus();
    unmount();
    expect(opener).toHaveFocus();
    opener.remove();
  });
});
