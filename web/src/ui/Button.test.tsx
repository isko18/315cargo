import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Button from './Button';

describe('Button', () => {
  it('рендерит текст и вызывает onClick', async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Сохранить</Button>);
    await userEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('в состоянии loading заблокирована и не кликается', async () => {
    const onClick = vi.fn();
    render(<Button loading onClick={onClick}>Отправить</Button>);
    const btn = screen.getByRole('button');
    expect(btn).toBeDisabled();
    await userEvent.click(btn);
    expect(onClick).not.toHaveBeenCalled();
  });

  it('вариант secondary даёт класс ghost', () => {
    render(<Button variant="secondary">X</Button>);
    expect(screen.getByRole('button').className).toContain('ghost');
  });

  it('disabled блокирует клик', async () => {
    const onClick = vi.fn();
    render(<Button disabled onClick={onClick}>X</Button>);
    await userEvent.click(screen.getByRole('button'));
    expect(onClick).not.toHaveBeenCalled();
  });
});
