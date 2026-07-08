import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { clearToken } from '../api';

export default function Layout() {
  const nav = useNavigate();
  const who = localStorage.getItem('who') || '';

  function logout() {
    clearToken();
    localStorage.removeItem('who');
    nav('/login', { replace: true });
  }

  return (
    <div className="app">
      <header className="topbar">
        <span className="logo">315CARGO</span>
        <nav>
          <NavLink to="/scan" className={({ isActive }) => (isActive ? 'active' : '')}>
            Приём по штрих-коду
          </NavLink>
          <NavLink to="/overview" className={({ isActive }) => (isActive ? 'active' : '')}>
            Все карго
          </NavLink>
        </nav>
        <span className="spacer" />
        {who && <span className="who">{who}</span>}
        <button className="ghost" onClick={logout}>
          Выйти
        </button>
      </header>
      <main className="container">
        <Outlet />
      </main>
    </div>
  );
}
