import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { SignOutButton } from '../features/auth/SignOutButton';
import { send, type SessionUser } from './api';
import { SessionProvider, useSession } from './session';

const first: SessionUser = { id: 14, username: 'fixture-first', full_name: 'First Fixture', roles: [], capabilities: [] };
const second: SessionUser = { ...first, id: 29, username: 'fixture-second', full_name: 'Second Fixture' };
type MeRead = { resolve: (response: Response) => void; reject: (error: Error) => void };

function transport() {
  const reads: MeRead[] = [];
  const writes: { path: string; operator: string | null }[] = [];
  // Deliberately deliver even aborted reads: cancellation alone can't prove a
  // response already queued by the transport won't change the screen or header.
  vi.stubGlobal('fetch', (url: URL, init: RequestInit = {}) => {
    const path = url.pathname;
    if ((init.method ?? 'GET') === 'GET' && path === '/api/v1/auth/me/') {
      return new Promise<Response>((resolve, reject) => { reads.push({ resolve, reject }); });
    }
    if (init.method === 'POST' && ['/api/v1/auth/logout/', '/api/v1/test-only/binding/'].includes(path)) {
      writes.push({ path, operator: new Headers(init.headers).get('X-Hotel-Operator') });
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    throw new Error(`Unexpected fixture request: ${path}`);
  });
  async function writeOperator() {
    await send('test-only/binding/', 'POST');
    return writes.at(-1)!.operator;
  }
  return { reads, writes, writeOperator };
}

function Probe() {
  const { user, loading, error } = useSession();
  if (loading) return <p role="status">Checking session</p>;
  if (error) return <p role="alert">{error}</p>;
  return <><p role="status">{user?.username ?? 'Signed out'}</p>{user && <SignOutButton />}</>;
}
function mount(strict = false) {
  const app = <MemoryRouter><SessionProvider><Probe /></SessionProvider></MemoryRouter>;
  return render(strict ? <StrictMode>{app}</StrictMode> : app);
}
async function answer(read: MeRead, user: SessionUser | null) {
  await act(async () => {
    read.resolve(new Response(JSON.stringify({ user }), { headers: { 'Content-Type': 'application/json' } }));
  });
}
function notify(event: Event) { act(() => { window.dispatchEvent(event); }); }
function expectStatus(text: string) { expect(screen.getByRole('status')).toHaveTextContent(text); }
afterEach(() => { vi.unstubAllGlobals(); });

it.each(['hms:operator-changed', 'storage'])('keeps the new operator when the old focus check returns last (%s)', async (source) => {
  const { reads, writeOperator } = transport();
  mount();
  await answer(reads[0], first);
  const signOut = screen.getByRole('button', { name: 'Sign out' });
  notify(new Event('focus'));
  expect(screen.getByRole('button', { name: 'Sign out' })).toBe(signOut);
  expect(await writeOperator()).toBe(String(first.id));

  notify(source === 'storage' ? new StorageEvent('storage', { key: 'hotel-a:session-change' }) : new Event(source));
  expectStatus('Checking session');
  expect(await writeOperator()).toBeNull();
  await answer(reads[2], second);
  expectStatus(second.username);
  await answer(reads[1], first);
  expectStatus(second.username);
  expect(await writeOperator()).toBe(String(second.id));
});

it('cannot re-admit an operator after the sign-out button posts logout and verifies a null session', async () => {
  const { reads, writes, writeOperator } = transport();
  mount();
  await answer(reads[0], first);
  notify(new Event('focus'));
  fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
  await waitFor(() => expect(reads).toHaveLength(3));
  expect(writes).toEqual([{ path: '/api/v1/auth/logout/', operator: String(first.id) }]);
  await answer(reads[2], null);
  expectStatus('Signed out');

  await answer(reads[1], first);
  expectStatus('Signed out');
  expect(await writeOperator()).toBeNull();
});

it('settles initial admission on expiration without waiting for the pending read', async () => {
  const { reads, writeOperator } = transport();
  mount();
  expectStatus('Checking session');
  notify(new Event('hms:session-expired'));
  expectStatus('Signed out');
  await answer(reads[0], first);
  expectStatus('Signed out');
  expect(await writeOperator()).toBeNull();
});

it.each(['success', 'failure'])('keeps admission pending when a superseded %s arrives before the new response', async (outcome) => {
  const { reads, writeOperator } = transport();
  mount();
  notify(new Event('focus'));
  if (outcome === 'success') await answer(reads[0], first);
  else await act(async () => { reads[0].reject(new Error('fixture transport failure')); });
  expectStatus('Checking session');
  expect(await writeOperator()).toBeNull();
  await answer(reads[1], second);
  expectStatus(second.username);
});

it('discards reads across StrictMode replay and real unmount without changing later write headers', async () => {
  const { reads, writeOperator } = transport();
  const view = mount(true);
  expect(reads).toHaveLength(2);
  await answer(reads[1], second);
  await answer(reads[0], first); // discarded StrictMode setup
  expectStatus(second.username);
  expect(await writeOperator()).toBe(String(second.id));

  notify(new Event('focus'));
  view.unmount();
  expect(await writeOperator()).toBeNull();
  mount();
  await answer(reads[3], first);
  await answer(reads[2], second); // even a different provider's global write binding must survive
  expectStatus(first.username);
  expect(await writeOperator()).toBe(String(first.id));
});
