import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { SessionProvider } from '../../services/session';
import { HousekeepingPage, ParkingPage } from './index';
import { OrderForm } from './restaurant/OrderForm';
import { MenuForm } from './restaurant/MenuForm';
import { type MenuItem } from './restaurant/model';
import { AllocationDesk } from './parking/AllocationDesk';
import { OrderDesk } from './restaurant/OrderDesk';

// Synthetic HTTP responses for isolated UI tests; the real session/api modules are in use.
function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
}
function paged<T,>(rows: T[]) { return json({ count: rows.length, next: null, previous: null, results: rows }); }
function account(capabilities: string[]) {
  return json({ user: { id: 9, username: 'synthetic', full_name: 'Test worker', roles: [], capabilities } });
}
function serve(handle: (path: string, url: URL, options: RequestInit) => Response) {
  const seen: string[] = [];
  vi.stubGlobal('fetch', async (input: URL | string, options: RequestInit = {}) => {
    const url = new URL(input);
    seen.push(`${options.method ?? 'GET'} ${url.pathname}`);
    return handle(url.pathname, url, options);
  });
  return seen;
}
afterEach(() => vi.unstubAllGlobals());

it('loads only the assigned maintenance queue and recovers from a list failure', async () => {
  const operator = userEvent.setup();
  let attempts = 0;
  const seen = serve((path) => {
    if (path === '/api/v1/auth/me/') return account(['maintenance.view', 'maintenance.work']);
    if (path === '/api/v1/maintenance/') {
      attempts += 1;
      return attempts === 1 ? json({ detail: 'Test interruption' }, 503) : paged([]);
    }
    return json({ detail: 'Not allowed in this test scope' }, 403);
  });
  render(<SessionProvider><HousekeepingPage /></SessionProvider>);
  expect(await screen.findByRole('alert')).toHaveTextContent('Test interruption');
  await operator.click(screen.getByRole('button', { name: 'Retry loading maintenance requests' }));
  expect(await screen.findByText('No maintenance requests match this view.')).toBeVisible();
  expect(screen.queryByRole('button', { name: /new maintenance|cleaning tasks/i })).not.toBeInTheDocument();
  expect(seen).toEqual(['GET /api/v1/auth/me/', 'GET /api/v1/maintenance/', 'GET /api/v1/maintenance/']);
});

it('does not request plates or allocations for an account without parking access', async () => {
  const seen = serve((path) => path === '/api/v1/auth/me/' ? account(['restaurant.view']) : json({}, 403));
  render(<SessionProvider><ParkingPage /></SessionProvider>);
  expect(await screen.findByRole('alert')).toHaveTextContent('does not have access to parking');
  expect(seen).toEqual(['GET /api/v1/auth/me/']);
});

it('confirms release before posting and retrieves the retained allocation through history', async () => {
  const operator = userEvent.setup();
  const row = { id: 22, space: 2, space_code: 'T-9', vehicle: 4, vehicle_plate: 'SYNTHETIC', started_at: '2026-02-02T09:00:00Z' };
  let end: string | null = null;
  let releases = 0;
  serve((path, url, options) => {
    if (path === '/api/v1/parking-allocations/22/release/' && options.method === 'POST' && options.body === '{}') {
      releases += 1; end = '2026-02-02T10:00:00Z'; return json({ ...row, ended_at: end });
    }
    if (path === '/api/v1/parking-allocations/') {
      const status = url.searchParams.get('status');
      return paged(status === (end ? 'released' : 'active') ? [{ ...row, ended_at: end }] : []);
    }
    return json({}, 404);
  });
  render(<div className="ops"><AllocationDesk manage /></div>);
  await operator.click(await screen.findByRole('button', { name: 'Release space' }));
  expect(releases).toBe(0);
  await operator.click(screen.getByRole('button', { name: 'Confirm release' }));
  expect(await screen.findByText('No vehicles are currently parked.')).toBeVisible();
  expect(releases).toBe(1);
  await operator.selectOptions(screen.getByLabelText('Allocation view'), 'released');
  const saved = await screen.findByRole('article', { name: 'Allocation 22' });
  expect(within(saved).getByText(row.vehicle_plate)).toBeVisible();
  expect(saved.querySelector('time[datetime="2026-02-02T10:00:00Z"]')).not.toBeNull();
  expect(within(saved).queryByRole('button', { name: 'Release space' })).not.toBeInTheDocument();
});

it('does not expose inspection or the staff directory to a housekeeper with a completed task', async () => {
  const seen = serve((path) => {
    if (path === '/api/v1/auth/me/') return account(['housekeeping.view', 'housekeeping.work']);
    if (path === '/api/v1/cleaning-tasks/') return paged([{
      id: 6, room: 12, room_number: 'T-1', assignee: 9, status: 'completed', notes: '', created_at: '2026-02-02T09:00:00Z',
    }]);
    return json({}, 403);
  });
  render(<SessionProvider><HousekeepingPage /></SessionProvider>);
  const task = await screen.findByRole('article', { name: 'Room T-1, cleaning task 6' });
  expect(within(task).getByText(/inspection is still required/i)).toBeVisible();
  expect(within(task).queryByRole('button')).not.toBeInTheDocument();
  expect(seen).toEqual(['GET /api/v1/auth/me/', 'GET /api/v1/cleaning-tasks/']);
});

const dish: MenuItem = { id: 3, category: 'Test category', name: 'Synthetic dish', price: '100.50', available: true, description: '', image: null };

it('submits a multi-line room ticket through scoped lookups and the versioned command', async () => {
  const operator = userEvent.setup();
  let submitted: unknown;
  const seen = serve((path, url, options) => {
    if (path === '/api/v1/menu-items/' && url.searchParams.get('available') === 'true') {
      return paged([dish, { ...dish, id: 4, name: 'Synthetic drink' }]);
    }
    if (path === '/api/v1/orders/stays/') return paged([{ id: 15, rooms: [{ id: 11, number: 'T-1' }, { id: 13, number: 'T-2' }] }]);
    if (path === '/api/v1/staff/assignees/' && url.searchParams.get('role') === 'Restaurant Staff') {
      return paged([{ id: 9, username: 'test', full_name: 'Test server' }]);
    }
    if (path === '/api/v1/orders/' && options.method === 'POST') {
      submitted = JSON.parse(String(options.body)); return json({ id: 31, total: '301.50' }, 201);
    }
    return json({ detail: 'Unexpected request' }, 400);
  });
  const done = vi.fn();
  render(<OrderForm done={done} cancel={vi.fn()} />);
  await operator.click(screen.getByLabelText('Room service'));
  await operator.selectOptions(screen.getByLabelText('Active stay'), await screen.findByRole('option', { name: /Stay #15/ }));
  expect(screen.getByLabelText('Service room')).toHaveValue(''); // Never silently pick the first of multiple rooms.
  await operator.selectOptions(screen.getByLabelText('Service room'), '13');
  await operator.selectOptions(screen.getByLabelText('Menu item (line 1)'), '3');
  await operator.clear(screen.getByLabelText('Quantity (line 1)'));
  await operator.type(screen.getByLabelText('Quantity (line 1)'), '2');
  await operator.click(screen.getByRole('button', { name: 'Add another item' }));
  const second = screen.getByLabelText('Menu item (line 2)');
  await operator.selectOptions(second, await within(second).findByRole('option', { name: /Synthetic drink/ }));
  await operator.selectOptions(screen.getByLabelText('Assign to (optional)'), '9');
  await operator.click(screen.getByRole('button', { name: 'Place order' }));
  await waitFor(() => expect(done).toHaveBeenCalledTimes(1));
  expect(submitted).toEqual({ reservation: 15, room: 13, assignee: 9, items: [{ menu_item: 3, quantity: 2 }, { menu_item: 4, quantity: 1 }] });
  expect(seen).not.toContain('GET /api/v1/reservations/');
});

it('changes a pending ticket assignment without sending a status or rewriting its lines', async () => {
  const operator = userEvent.setup();
  const order = { id: 8, reservation: null, room: null, status: 'pending', items: [], total: '0.00', created_at: '2026-02-02T09:00:00Z' };
  let assignee: number | null = null;
  let patch: unknown;
  const seen = serve((path, url, options) => {
    if (path === '/api/v1/orders/') return paged([{ ...order, assignee }]);
    if (path === '/api/v1/staff/assignees/' && url.searchParams.get('role') === 'Restaurant Staff') {
      return paged([{ id: 12, full_name: 'Test colleague', username: 'synthetic' }]);
    }
    if (path === '/api/v1/orders/8/' && options.method === 'PATCH') {
      patch = JSON.parse(String(options.body)); assignee = 12;
      return json({ ...order, assignee, assignee_name: 'Test colleague' });
    }
    return json({}, 404);
  });
  render(<OrderDesk work />);
  await operator.click(await screen.findByRole('button', { name: 'Assign order' }));
  await operator.selectOptions(screen.getByLabelText('Assign to'), await screen.findByRole('option', { name: 'Test colleague' }));
  await operator.click(screen.getByRole('button', { name: 'Save assignment' }));
  expect(await screen.findByText('Order #8 assigned to Test colleague.')).toBeVisible();
  expect(patch).toEqual({ assignee: 12 });
  expect(seen).not.toContain('POST /api/v1/orders/8/transition/');
});

it('edits only menu availability without clearing the existing photo or overwriting an unrelated edit', async () => {
  const operator = userEvent.setup();
  let sent: unknown;
  const seen = serve((_path, _url, options) => {
    sent = JSON.parse(String(options.body));
    return json({ ...dish, available: false });
  });
  const done = vi.fn();
  render(<MenuForm item={{ ...dish, image: '/api/v1/private/test-image/' }} done={done} cancel={vi.fn()} />);
  await operator.click(screen.getByLabelText('Available to order'));
  await operator.click(screen.getByRole('button', { name: 'Save menu changes' }));
  await waitFor(() => expect(done).toHaveBeenCalledTimes(1));
  expect(seen).toEqual(['PATCH /api/v1/menu-items/3/']);
  expect(sent).toEqual({ available: false });
});

it('replaces a menu photo with multipart and lets the browser supply its boundary', async () => {
  const operator = userEvent.setup();
  let sent: { name: string; keys: string[]; contentType: string | null } | null = null;
  const seen = serve((_path, _url, options) => {
    if (options.body instanceof FormData) {
      const image = options.body.get('image');
      sent = { name: image instanceof File ? image.name : '', keys: [...options.body.keys()], contentType: new Headers(options.headers).get('Content-Type') };
    }
    return json(dish);
  });
  const done = vi.fn();
  render(<MenuForm item={{ ...dish, image: '/api/v1/private/test-image/' }} done={done} cancel={vi.fn()} />);
  await operator.upload(screen.getByLabelText('Replace image (optional)'), new File(['test upload'], 'test.png', { type: 'image/png' }));
  await operator.click(screen.getByRole('button', { name: 'Save menu changes' }));
  await waitFor(() => expect(done).toHaveBeenCalledTimes(1));
  expect(seen).toEqual(['PATCH /api/v1/menu-items/3/']);
  expect(sent).toEqual({ name: 'test.png', keys: ['image'], contentType: null });
});
