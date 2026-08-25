import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

/**
 * Тема панели: `auto` следует за системой, `light`/`dark` — принудительно.
 * Выбор хранится в localStorage под тем же ключом, что и inline-скрипт в
 * index.html (он применяет тему до первой отрисовки, чтобы не мигало).
 */
export type ThemeMode = 'auto' | 'light' | 'dark';
export type Resolved = 'light' | 'dark';

const KEY = 'theme';
const DARK_BG = '#0b1120';
const LIGHT_BG = '#f2f5f9';

function readMode(): ThemeMode {
  const raw = typeof localStorage !== 'undefined' ? localStorage.getItem(KEY) : null;
  return raw === 'dark' || raw === 'light' ? raw : 'auto';
}

function systemPrefersDark(): boolean {
  return typeof window !== 'undefined' && !!window.matchMedia
    ? window.matchMedia('(prefers-color-scheme: dark)').matches
    : false;
}

export function resolveMode(mode: ThemeMode): Resolved {
  if (mode === 'auto') return systemPrefersDark() ? 'dark' : 'light';
  return mode;
}

function applyTheme(resolved: Resolved) {
  const root = document.documentElement;
  root.setAttribute('data-theme', resolved);
  root.style.colorScheme = resolved;
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', resolved === 'dark' ? DARK_BG : LIGHT_BG);
}

type Ctx = { mode: ThemeMode; resolved: Resolved; setMode: (m: ThemeMode) => void; cycle: () => void };

const ThemeCtx = createContext<Ctx>({
  mode: 'auto',
  resolved: 'light',
  setMode: () => {},
  cycle: () => {},
});

const ORDER: ThemeMode[] = ['auto', 'light', 'dark'];

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(readMode);
  const [resolved, setResolved] = useState<Resolved>(() => resolveMode(readMode()));

  const setMode = useCallback((m: ThemeMode) => {
    setModeState(m);
    localStorage.setItem(KEY, m);
    const r = resolveMode(m);
    setResolved(r);
    applyTheme(r);
  }, []);

  const cycle = useCallback(() => {
    setMode(ORDER[(ORDER.indexOf(readMode()) + 1) % ORDER.length]);
  }, [setMode]);

  // В режиме `auto` следим за системным переключением темы на лету.
  useEffect(() => {
    applyTheme(resolveMode(mode));
    if (mode !== 'auto' || !window.matchMedia) return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => {
      const r: Resolved = mq.matches ? 'dark' : 'light';
      setResolved(r);
      applyTheme(r);
    };
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, [mode]);

  const value = useMemo(() => ({ mode, resolved, setMode, cycle }), [mode, resolved, setMode, cycle]);
  return <ThemeCtx.Provider value={value}>{children}</ThemeCtx.Provider>;
}

export function useTheme() {
  return useContext(ThemeCtx);
}
