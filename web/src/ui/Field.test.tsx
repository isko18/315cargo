import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Field, Input, Select } from './Field';

describe('Field', () => {
  it('связывает подпись с контролом — клик по label фокусирует поле', async () => {
    render(
      <Field label="Вес">
        <Input />
      </Field>,
    );
    const input = screen.getByLabelText('Вес');
    await userEvent.click(screen.getByText('Вес'));
    expect(input).toHaveFocus();
  });

  it('связывает подпись с select', () => {
    render(
      <Field label="Статус">
        <Select>
          <option value="a">A</option>
        </Select>
      </Field>,
    );
    expect(screen.getByLabelText('Статус')).toBeInstanceOf(HTMLSelectElement);
  });

  it('helper подключается через aria-describedby', () => {
    render(
      <Field label="Код" helper="латиницей">
        <Input />
      </Field>,
    );
    expect(screen.getByLabelText('Код')).toHaveAccessibleDescription('латиницей');
  });

  it('ошибка помечает поле как невалидное и описывает причину', () => {
    render(
      <Field label="Телефон" error="Неверный формат">
        <Input />
      </Field>,
    );
    const input = screen.getByLabelText('Телефон');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAccessibleDescription('Неверный формат');
  });

  it('явный htmlFor + id не переопределяются автогенерацией', () => {
    render(
      <Field label="Логин" htmlFor="login">
        <Input id="login" />
      </Field>,
    );
    expect(screen.getByLabelText('Логин')).toHaveAttribute('id', 'login');
  });

  it('иконка и суффикс не мешают связке label ↔ input', () => {
    render(
      <Field label="Вес">
        <Input suffix="кг" />
      </Field>,
    );
    expect(screen.getByLabelText('Вес')).toBeInstanceOf(HTMLInputElement);
  });
});
