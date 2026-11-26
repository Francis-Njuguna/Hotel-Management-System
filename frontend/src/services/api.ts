export interface Page<T> { count: number; next: string | null; previous: string | null; results: T[] }
export interface SessionUser { id: number; username: string; full_name: string; roles: string[]; capabilities: string[] }
let displayedOperator: number | null = null;
export function bindOperator(id: number | null) { displayedOperator=id; }
export class ApiError extends Error {
  constructor(public status: number, public data: unknown, message: string) { super(message); }
}
function messageOf(value: unknown): string {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map(messageOf).join('; ');
  if (value !== null && typeof value === 'object') {
    const obj = value as Record<string, unknown>;
    if (obj.detail) return messageOf(obj.detail);
    return Object.entries(obj).map(([k,v]) => `${k}: ${messageOf(v)}`).join('; ');
  }
  return '';
}
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const method = (options.method ?? 'GET').toUpperCase();
  if (!['GET','HEAD','OPTIONS'].includes(method)) {
    if (displayedOperator !== null && !path.startsWith('auth/login/')) headers.set('X-Hotel-Operator',String(displayedOperator));
    const csrf = document.cookie.split(';').map(x => x.trim()).find(x => x.startsWith('csrftoken='))?.slice(10);
    if (csrf) headers.set('X-CSRFToken', decodeURIComponent(csrf));
    if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) headers.set('Content-Type','application/json');
  }
  const url = new URL(`/api/v1/${path.replace(/^\/+/, '')}`, window.location.origin);
  if (!url.pathname.startsWith('/api/v1/')) throw new Error('Invalid API path');
  const response = await fetch(url, { ...options, headers, credentials: 'same-origin' });
  const json = response.headers.get('content-type')?.includes('json');
  const data: unknown = response.status === 204 ? null : json ? await response.json() : null;
  if (!response.ok) {
    if ((data as {code?:string}|null)?.code === 'not_authenticated') window.dispatchEvent(new Event('hms:session-expired'));
    if ((data as {code?:string}|null)?.code === 'operator_changed') window.dispatchEvent(new Event('hms:operator-changed'));
    throw new ApiError(response.status, data, messageOf(data) || `Request failed (${response.status}).`);
  }
  if (!json && response.status !== 204) throw new Error('The server returned an unexpected response. Refresh before trying again.');
  if (method==='POST' && ['auth/login/','auth/logout/','auth/reset/confirm/'].includes(path)) {
    try { localStorage.setItem('hotel-a:session-change',String(Date.now())); } catch { /* storage is optional */ }
  }
  return data as T;
}
export function send<T>(path: string, method: 'POST' | 'PATCH', body?: unknown): Promise<T> {
  return api<T>(path, { method, body: body instanceof FormData ? body : JSON.stringify(body ?? {}) });
}
export const can = (user: SessionUser | null, capability: string) => !!user?.capabilities.includes(capability);
