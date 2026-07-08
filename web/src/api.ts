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

export class ApiError extends Error {
  status: number;
  data: any;
  constructor(status: number, data: any) {
    super((data && (data.detail || data.error)) || `HTTP ${status}`);
    this.status = status;
    this.data = data;
  }
}

export async function api<T = any>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(opts.headers as Record<string, string> | undefined),
  };
  const t = getToken();
  if (t) headers['Authorization'] = `Bearer ${t}`;

  const res = await fetch(BASE + path, { ...opts, headers });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new ApiError(res.status, data);
  return data as T;
}

export const get = <T = any>(p: string) => api<T>(p);
export const post = <T = any>(p: string, body?: unknown) =>
  api<T>(p, { method: 'POST', body: body ? JSON.stringify(body) : undefined });
export const patch = <T = any>(p: string, body?: unknown) =>
  api<T>(p, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined });
