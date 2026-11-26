// Synthetic component-test transport only. No runtime feature imports this module.
import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, vi } from 'vitest';
import type { Page } from '../../../services/api';
import { SessionProvider } from '../../../services/session';
import type { Guest, Reservation, Room } from '../model';

export const guest: Guest = { id: 12, full_name: 'Test Guest Alpha', reference: 'TEST-G12', email: 'alpha@example.test', phone: '' };
export const room: Room = {
  id: 4, number: 'T04', category: 'Twin', capacity: 2, description: '', facilities: ['Desk'], image: null,
  nightly_rate: '2450.50', cleanliness: 'inspected', occupied: false, maintenance: false, is_active: true,
};
export const otherRoom: Room = { ...room, id: 7, number: 'T07', nightly_rate: '3010.05' };
export const stay: Reservation = {
  id: 39, guest: guest.id, guest_name: guest.full_name, arrival: '2029-03-10', departure: '2029-03-12',
  status: 'confirmed', rooms: [{ id: room.id, number: room.number, nightly_rate: room.nightly_rate }],
  events: [{ id: 1, status: 'confirmed', note: 'Test booking confirmed.', created_at: '2029-03-01T12:00:00Z' }],
};

export function pageOf<T>(results: T[], extra: Partial<Page<T>> = {}): Page<T> {
  return { results, count: results.length, previous: null, next: null, ...extra };
}

interface Call { path: string; params: URLSearchParams; method: string; body: unknown; headers: Headers }
interface Reply { data: unknown; status?: number }
type Respond = (call: Call) => Reply | Promise<Reply>;
const all = ['guests.view', 'guests.manage', 'rooms.view', 'rooms.manage', 'reservations.view', 'reservations.manage', 'billing.view'];

export function openPage(element: ReactElement, respond: Respond, capabilities = all, entry = '/') {
  const calls: Call[] = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, options: RequestInit = {}) => {
    const url = new URL(String(input), window.location.origin);
    if (!url.pathname.startsWith('/api/v1/')) throw new Error('Unexpected test request outside versioned API.');
    const call: Call = {
      path: url.pathname.slice('/api/v1/'.length), params: url.searchParams, method: options.method ?? 'GET',
      body: typeof options.body === 'string' ? JSON.parse(options.body) : options.body, headers: new Headers(options.headers),
    };
    calls.push(call);
    const reply: Reply = call.path === 'auth/me/' ? { data: { user: { id: 1, username: 'test-staff', full_name: 'Test Staff', roles: [], capabilities } } }
      : await respond(call);
    return new Response(JSON.stringify(reply.data), { status: reply.status ?? 200, headers: { 'Content-Type': 'application/json' } });
  }));
  render(<MemoryRouter initialEntries={[entry]}><SessionProvider>{element}</SessionProvider></MemoryRouter>);
  return calls;
}

afterEach(() => { vi.unstubAllGlobals(); });
