import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, type SessionUser } from '../../services/api';
import { useSession } from '../../services/session';
import { OverviewPage } from './OverviewPage';

vi.mock('../../services/api', async (original) => ({ ...await original<typeof import('../../services/api')>(), api: vi.fn() }));
vi.mock('../../services/session', async (original) => ({ ...await original<typeof import('../../services/session')>(), useSession: vi.fn() }));
const get = vi.mocked(api);
const session = vi.mocked(useSession);
const date = '2026-11-26';
function actor(capabilities: string[]) {
  const user: SessionUser = { id: 7, username: 'fixture', full_name: 'Fixture Staff', roles: [], capabilities: ['dashboard.view', ...capabilities] };
  session.mockReturnValue({ user, loading: false, error: null, refresh: vi.fn().mockResolvedValue(undefined) });
  render(<MemoryRouter><OverviewPage /></MemoryRouter>);
}

describe('live overview projections', () => {
  beforeEach(() => { get.mockReset(); session.mockReset(); });
  it('distinguishes pending, failed, genuine zero, empty and omitted metrics; retry reads the API again', async () => {
    get.mockRejectedValueOnce(new Error('fixture network failure')).mockResolvedValueOnce({ date, metrics: { check_ins: 0 }, reservations: [] });
    actor(['reservations.view']);
    expect(screen.getByText('Loading your shift overview…')).toBeVisible();
    expect(screen.queryByText('No reservations in this briefing')).not.toBeInTheDocument();
    expect(await screen.findByRole('alert')).toHaveTextContent('could not be loaded');
    expect(screen.queryByText('Check-ins')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    const tile = await screen.findByRole('link', { name: /check-ins/i });
    expect(within(tile).getByText('0')).toBeVisible(); expect(within(tile).getByText('Scheduled today')).toBeVisible();
    expect(tile).toHaveAttribute('href', '/reservations');
    expect(screen.getByText('No reservations in this briefing')).toBeVisible();
    expect(screen.queryByText('Check-outs')).not.toBeInTheDocument();
    expect(screen.getByText('Shift overview refreshed.')).toBeInTheDocument();
    expect(get.mock.calls.map(([path]) => path)).toEqual(['dashboard/', 'dashboard/']);
  });
  it('renders the restaurant queue but no guest rows, financial figures or room links outside the actor’s grants', async () => {
    get.mockResolvedValueOnce({ date, metrics: { total_guests: 42, collected: '875.50', occupied_rooms: 2 },
      orders: [{ id: 14, status: 'ready' }], tasks: [{ id: 2, room_number: 'Fixture room', status: 'assigned' }],
      reservations: [{ id: 1, guest_name: 'Out-of-scope fixture', arrival: date, departure: '2026-11-29', status: 'confirmed' }] });
    actor(['restaurant.view', 'restaurant.work']);
    const orders = within(await screen.findByRole('region', { name: 'Service orders' }));
    expect(orders.getByText('Order #14')).toBeVisible(); expect(orders.getByText('Ready')).toBeVisible();
    const ready = screen.getByRole('link', { name: /ready to serve/i });
    expect(ready).toHaveAttribute('href', '/restaurant'); expect(within(ready).getByText('1')).toBeVisible();
    expect(screen.queryByText(/out-of-scope fixture|875\.50|fixture room|guest profiles/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Reservation board' })).not.toBeInTheDocument();
    expect(get.mock.calls.map(([path]) => path)).toEqual(['dashboard/']);
  });
  it('filters by the API property day, links actual booking IDs and keeps cancelled stays out of the arrivals filter', async () => {
    get.mockResolvedValueOnce({ date, metrics: { check_ins: 1, check_outs: 0 }, reservations: [
      { id: 31, guest_name: 'Fixture Arrival', arrival: date, departure: '2026-11-30', status: 'confirmed' },
      { id: 32, guest_name: 'Fixture Cancelled', arrival: date, departure: '2026-11-28', status: 'cancelled' },
      { id: 33, guest_name: 'Fixture Later', arrival: '2026-11-27', departure: '2026-11-29', status: 'confirmed' },
    ] });
    actor(['reservations.view']);
    const board = within(await screen.findByRole('region', { name: 'Reservation board' }));
    expect(screen.getAllByText('Scheduled today')).toHaveLength(2);
    expect(board.getAllByRole('row')).toHaveLength(4);
    await userEvent.click(board.getByRole('button', { name: 'Arriving today' }));
    expect(board.getAllByRole('row')).toHaveLength(2);
    expect(board.getByRole('link', { name: 'View history for reservation #31' })).toHaveAttribute('href', '/reservations?reservation=31');
    await userEvent.click(board.getByRole('button', { name: 'Leaving today' }));
    expect(board.getByText('No matching stays')).toBeVisible(); expect(board.queryByRole('table')).not.toBeInTheDocument();
  });
  it('keeps charges distinct from received tender and links finance to actual invoices', async () => {
    get.mockResolvedValueOnce({ date, metrics: { billed: '4850.25', collected: '2000.00' } })
      .mockResolvedValueOnce({ count: 1, next: null, previous: null, results: [{ id: 5, balance: '2850.25', total: '4850.25', closed_at: null }] });
    actor(['billing.view', 'billing.manage']);
    const snapshot = within(await screen.findByRole('region', { name: 'Shift snapshot' }));
    expect(snapshot.getByRole('link', { name: /billed today/i })).toHaveTextContent('4,850.25');
    expect(snapshot.getByRole('link', { name: /collected today/i })).toHaveTextContent('2,000.00');
    const invoices = within(await screen.findByRole('region', { name: 'Invoice register' }));
    expect(await invoices.findByText('Invoice #5')).toBeVisible();
    expect(invoices.getByText('KES 2,850.25')).toBeVisible();
    expect(get.mock.calls.map(([path]) => path)).toEqual(['dashboard/', 'invoices/?page_size=5']);
  });
});
