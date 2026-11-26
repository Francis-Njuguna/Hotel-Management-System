import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ReservationsPage } from '../ReservationsPage';
import { openPage, pageOf, stay } from './harness';

describe('Reservation lifecycle', () => {
  it.each([
    ['pending', 'Confirm reservation', 'confirm', 'confirmed'],
    ['confirmed', 'Cancel reservation', 'cancel', 'cancelled'],
    ['confirmed', 'Check in', 'check_in', 'checked_in'],
    ['checked_in', 'Check out', 'check_out', 'checked_out'],
  ] as const)('requires confirmation before %s → %s', async (before, label, action, after) => {
    let current = before as string;
    const calls = openPage(<ReservationsPage />, ({ path, method }) => {
      if (method === 'POST') current = after;
      const data = { ...stay, status: current };
      return { data: path === 'reservations/' ? pageOf([data]) : data };
    });
    fireEvent.click(await screen.findByRole('button', { name: `${label} · #39` }));
    const dialog = within(screen.getByRole('dialog', { name: `${label} · #39` }));
    await waitFor(() => expect(dialog.getByRole('button', { name: label })).toBeEnabled());
    expect(calls.some(c => c.method === 'POST')).toBe(false);
    fireEvent.click(dialog.getByRole('button', { name: label }));
    expect(await screen.findByText(`Reservation #39 updated for Test Guest Alpha. Status: ${after.replaceAll('_', ' ')}.`)).toBeVisible();
    expect(calls.filter(c => c.method === 'POST')).toHaveLength(1);
    expect(calls.find(c => c.method === 'POST')).toMatchObject({ path: `reservations/39/${action}/`, body: {} });
  });

  it('displays a rejected checkout without closing the stay or recording a payment', async () => {
    const data = { ...stay, status: 'checked_in' };
    const calls = openPage(<ReservationsPage />, ({ path, method }) => method === 'POST'
      ? { status: 409, data: { detail: 'Outstanding folio balance: KES 580.25.' } }
      : { data: path === 'reservations/' ? pageOf([data]) : data });
    fireEvent.click(await screen.findByRole('button', { name: 'Check out · #39' }));
    const dialog = within(screen.getByRole('dialog', { name: 'Check out · #39' }));
    await waitFor(() => expect(dialog.getByRole('button', { name: 'Check out' })).toBeEnabled());
    fireEvent.click(dialog.getByRole('button', { name: 'Check out' }));
    expect(await dialog.findByRole('alert')).toHaveTextContent('Outstanding folio balance: KES 580.25.');
    expect(screen.queryByText(/Status: checked out/)).not.toBeInTheDocument();
    fireEvent.click(dialog.getByRole('button', { name: 'Go back' }));
    expect(await screen.findByRole('button', { name: 'Check out · #39' })).toBeEnabled();
    expect(calls.filter(c => c.method !== 'GET').map(c => c.path)).toEqual(['reservations/39/check_out/']);
  });

  it('does not dispatch a second cancellation while the first is awaiting a response', async () => {
    let finish!: () => void;
    const calls = openPage(<ReservationsPage />, ({ path, method }) => {
      if (method === 'POST') return new Promise<{data: unknown}>(resolve => { finish = () => resolve({ data: { ...stay, status: 'cancelled' } }); });
      return { data: path === 'reservations/' ? pageOf([stay]) : stay };
    });
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel reservation · #39' }));
    const dialog = within(screen.getByRole('dialog', { name: 'Cancel reservation · #39' }));
    const button = dialog.getByRole('button', { name: 'Cancel reservation' });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button); fireEvent.click(button);
    expect(button).toBeDisabled(); expect(dialog.getByRole('button', { name: 'Go back' })).toBeDisabled();
    expect(calls.filter(call => call.method === 'POST')).toHaveLength(1);
    await act(async () => { finish(); });
    expect(await screen.findByText(/Status: cancelled/)).toBeVisible();
  });

  it('loads real event detail on demand for a read-only viewer', async () => {
    const calls = openPage(<ReservationsPage />, ({ path }) => ({ data: path === 'reservations/39/' ? stay : pageOf([{ ...stay, events: undefined }]) }), ['reservations.view']);
    fireEvent.click(await screen.findByRole('button', { name: 'History for reservation #39' }));
    const dialog = within(screen.getByRole('dialog', { name: 'Reservation #39 history' }));
    expect(await dialog.findByText('Test booking confirmed.')).toBeVisible();
    expect(screen.queryByRole('button', { name: /Amend|Check in|New reservation/ })).not.toBeInTheDocument();
    expect(calls.filter(c => c.path === 'reservations/39/')).toHaveLength(1);
  });
});
