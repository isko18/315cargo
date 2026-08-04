const BASE = (import.meta.env.VITE_API_BASE as string) || 'https://315cargo.webtm.ru';

export function getToken(): string {
  return localStorage.getItem('access') || '';
}
export function setToken(t: string) {
  localStorage.setItem('access', t);
}
export function clearToken() {
  localStorage.removeItem('access');
}

export function getRefresh(): string {
  return localStorage.getItem('refresh') || '';
}
export function setRefresh(t: string) {
  if (t) localStorage.setItem('refresh', t);
}
export function clearRefresh() {
  localStorage.removeItem('refresh');
}

export type Role = {
  is_china_staff?: boolean;
  is_cargo_admin?: boolean;
  is_superuser?: boolean;
  is_staff?: boolean;
  allowed_tabs?: string[];
  pickup_point?: number | null;
};
export function setRole(r: Role) {
  localStorage.setItem('role', JSON.stringify(r));
}
export function getRole(): Role {
  try {
    return JSON.parse(localStorage.getItem('role') || '{}');
  } catch {
    return {};
  }
}
export function clearRole() {
  localStorage.removeItem('role');
}
export function isChinaOnly(r: Role = getRole()): boolean {
  return Boolean(r.is_china_staff && !r.is_cargo_admin && !r.is_superuser);
}
// Оператор привязан к одному ПВЗ: сервер жёстко ограничивает его склад этим
// ПВЗ, а переключатель ПВЗ для него не нужен (и мог бы спрятать его посылки).
export function isPickupBound(r: Role = getRole()): boolean {
  return Boolean(
    r.is_staff && !r.is_cargo_admin && !r.is_superuser && !r.is_china_staff && r.pickup_point,
  );
}
export function allowedTabs(r: Role = getRole()): string[] {
  return Array.isArray(r.allowed_tabs) ? r.allowed_tabs : [];
}
export function canAccessTab(tab: string, r: Role = getRole()): boolean {
  return allowedTabs(r).includes(tab);
}

export class ApiError extends Error {
  status: number;
  data: any;
  constructor(status: number, data: any) {
    super((data && (data.detail || data.error)) || `HTTP ${status}`);
    this.status = status;
    this.data = data;
  }
}

// Обновление access по refresh. Single-flight: параллельные 401 ждут один запрос.
let refreshPromise: Promise<string> | null = null;

async function doRefresh(): Promise<string> {
  const refresh = getRefresh();
  if (!refresh) throw new Error('no refresh token');
  const res = await fetch(BASE + '/api/auth/refresh/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh }),
  });
  if (!res.ok) throw new Error('refresh failed');
  const data = await res.json();
  setToken(data.access);
  if (data.refresh) setRefresh(data.refresh); // ROTATE_REFRESH_TOKENS на бэке
  return data.access;
}

function refreshAccess(): Promise<string> {
  if (!refreshPromise) {
    refreshPromise = doRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

function forceLogout() {
  clearToken();
  clearRefresh();
  localStorage.removeItem('role');
  localStorage.removeItem('who');
  if (!location.pathname.startsWith('/login')) location.assign('/login');
}

export async function api<T = any>(path: string, opts: RequestInit = {}, retry = false): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(opts.headers as Record<string, string> | undefined),
  };
  // Не прикрепляем токен к auth-эндпоинтам: протухший access иначе даёт
  // 401 «token not valid» на самом логине (SimpleJWT отвергает плохой токен
  // до проверки прав, несмотря на AllowAny).
  const isAuthEndpoint = path.startsWith('/api/auth/');
  const t = getToken();
  if (t && !isAuthEndpoint) headers['Authorization'] = `Bearer ${t}`;

  const res = await fetch(BASE + path, { ...opts, headers });
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }

  if (!res.ok) {
    // Access истёк → один раз обновляем по refresh и повторяем запрос.
    if (res.status === 401 && !isAuthEndpoint && !retry && getRefresh()) {
      try {
        await refreshAccess();
      } catch {
        forceLogout();
        throw new ApiError(res.status, data);
      }
      return api<T>(path, opts, true);
    }
    throw new ApiError(res.status, data);
  }
  return data as T;
}

export const get = <T = any>(p: string) => api<T>(p);
export const post = <T = any>(p: string, body?: unknown) =>
  api<T>(p, { method: 'POST', body: body ? JSON.stringify(body) : undefined });
export const patch = <T = any>(p: string, body?: unknown) =>
  api<T>(p, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined });
