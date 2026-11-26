// Synthetic component-test transport only. Production pages always call the shared session/API services.
import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { vi } from 'vitest';
import type { Page, SessionUser } from '../../../services/api';
import { SessionProvider } from '../../../services/session';

export type Call = { path: string; method: string; body: unknown };
export function paged<T>(results: T[], more: Partial<Omit<Page<T>, 'results'>> = {}): Page<T> {
  return { count: results.length, next: null, previous: null, ...more, results };
}

export function mountOffice(element: ReactElement, capabilities: string[], route: (call: Call) => unknown) {
  const calls: Call[] = [];
  const user: SessionUser = { id: 8, username: 'fixture-operator', full_name: 'Test Operator', roles: [], capabilities };
  vi.stubGlobal('fetch', vi.fn(async (input: URL, options: RequestInit) => {
    const url = new URL(input);
    if (url.origin !== window.location.origin || !url.pathname.startsWith('/api/v1/')) throw new Error('Unexpected API origin or prefix');
    const call = {
      path: url.pathname.slice('/api/v1/'.length) + url.search, method: options.method ?? 'GET',
      body: typeof options.body === 'string' ? JSON.parse(options.body) as unknown : undefined,
    };
    calls.push(call);
    const result = call.path === 'auth/me/' && call.method === 'GET' ? { user } : await route(call);
    if (result instanceof Response) return result;
    return new Response(JSON.stringify(result), { headers: { 'Content-Type': 'application/json' } });
  }));
  render(<SessionProvider>{element}</SessionProvider>);
  return calls;
}
