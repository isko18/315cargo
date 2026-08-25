import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import BottomNav from './BottomNav';
import { I18nProvider } from '../i18n';

function setRole(tabs: string[] | null) {
  localStorage.setItem(
    'role',
    JSON.stringify({
      is_superuser: false,
      is_staff: true,
      is_cargo_admin: false,
      is_china_staff: false,
      allowed_tabs: tabs,
      pickup_point: null,
    }),
  );
}

function setup(onMore = vi.fn(), path = '/scan') {
  render(
    <I18nProvider>
      <MemoryRouter initialEntries={[path]}>
        <BottomNav onMore={onMore} />
      </MemoryRouter>
    </I18nProvider>,
  );
  return onMore;
}

afterEach(() => localStorage.clear());

describe('BottomNav', () => {
  it('показывает основные разделы по приоритету и кнопку «Ещё»', () => {
    setRole(['warehouse', 'issue', 'scan', 'clients', 'staff']);
    setup();
    // Порядок фиксированный: приём → выдача → склад, независимо от прав.
    const labels = screen.getAllByRole('link').map((a) => a.textContent);
    expect(labels).toEqual(['Приём', 'Выдача', 'Склад']);
    expect(screen.getByText('Ещё')).toBeInTheDocument();
  });

  it('не показывает разделы без доступа', () => {
    setRole(['scan', 'china']);
    setup();
    const labels = screen.getAllByRole('link').map((a) => a.textContent);
    expect(labels).toEqual(['Приём', 'Склад Китай']);
    expect(screen.queryByText('Выдача')).not.toBeInTheDocument();
  });

  it('подсвечивает текущий раздел', () => {
    setRole(['scan', 'issue', 'warehouse']);
    setup(vi.fn(), '/issue');
    expect(screen.getByRole('link', { name: 'Выдача' })).toHaveClass('active');
    expect(screen.getByRole('link', { name: 'Приём' })).not.toHaveClass('active');
  });

  it('«Ещё» открывает боковое меню', async () => {
    setRole(['scan', 'issue', 'warehouse']);
    const onMore = setup();
    await userEvent.click(screen.getByText('Ещё'));
    expect(onMore).toHaveBeenCalled();
  });

  it('не рендерится, когда доступен один раздел — хватит бургера', () => {
    setRole(['scan']);
    const { container } = render(
      <I18nProvider>
        <MemoryRouter initialEntries={['/scan']}>
          <BottomNav onMore={vi.fn()} />
        </MemoryRouter>
      </I18nProvider>,
    );
    expect(container.querySelector('.bottom-nav')).toBeNull();
  });
});
