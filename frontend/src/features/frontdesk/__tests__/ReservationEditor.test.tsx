import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ReservationsPage } from '../ReservationsPage';
import { guest, openPage, otherRoom, pageOf, room, stay } from './harness';

describe('Reservation editor', () => {
  it('opens a guest-linked booking and ignores a late availability response for the old dates', async () => {
    let finish!: () => void;
    const calls = openPage(<ReservationsPage />, ({ path, params }) => {
      if (path === `guests/${guest.id}/`) return { data: guest };
      if (path === 'rooms/availability/' && params.get('departure') === stay.departure) {
        return new Promise<{data: unknown}>(resolve => { finish = () => resolve({ data: pageOf([room]) }); });
      }
      return { data: pageOf(path === 'rooms/availability/' ? [otherRoom] : []) };
    }, undefined, `/reservations?new_for=${guest.id}`);
    const change = await screen.findByRole('button', { name: 'Change guest' });
    const dialog = within(change.closest('dialog')!);
    expect(dialog.getByText(guest.full_name)).toBeVisible();
    fireEvent.change(dialog.getByLabelText('Arrival date'), { target: { value: stay.arrival } });
    fireEvent.change(dialog.getByLabelText('Departure date'), { target: { value: stay.departure } });
    await waitFor(() => expect(finish).toBeTypeOf('function'));
    fireEvent.change(dialog.getByLabelText('Departure date'), { target: { value: '2029-03-15' } });
    expect(await dialog.findByRole('checkbox', { name: /Room T07/ })).toBeVisible();
    await act(async () => { finish(); });
    expect(dialog.queryByRole('checkbox', { name: /Room T04/ })).not.toBeInTheDocument();
    expect(calls.some(call => call.path === 'guests/')).toBe(false);
  });

  it('selects rooms across availability pages and submits one pending multi-room command', async () => {
    const calls = openPage(<ReservationsPage />, ({ path, method, params }) => {
      if (path === 'reservations/') return method === 'POST' ? { status: 201, data: { ...stay, status: 'pending', rooms: [room, otherRoom] } } : { data: pageOf([]) };
      if (path === 'guests/') return { data: pageOf([guest]) };
      if (path === 'rooms/availability/') return { data: params.get('page') === '2' ? pageOf([otherRoom], { count: 7, previous: '?page=1' }) : pageOf([room], { count: 7, next: '?page=2' }) };
      throw new Error(`Unexpected ${path}`);
    });
    fireEvent.click(await screen.findByRole('button', { name: 'New reservation' }));
    const dialog = within(screen.getByRole('dialog', { name: 'New reservation' }));
    fireEvent.click(await dialog.findByRole('button', { name: /^Select Test Guest Alpha/ }));
    expect(calls.some(c => c.path === 'rooms/availability/')).toBe(false);
    fireEvent.change(dialog.getByLabelText('Arrival date'), { target: { value: stay.arrival } });
    fireEvent.change(dialog.getByLabelText('Departure date'), { target: { value: stay.departure } });
    fireEvent.click(await dialog.findByRole('checkbox', { name: /Room T04/ }));
    fireEvent.click(dialog.getByRole('button', { name: 'Next page of available rooms' }));
    fireEvent.click(await dialog.findByRole('checkbox', { name: /Room T07/ }));
    expect(dialog.getByRole('list', { name: 'Selected rooms' })).toHaveTextContent('Room T04');
    expect(dialog.getByRole('list', { name: 'Selected rooms' })).toHaveTextContent('Room T07');
    fireEvent.change(dialog.getByLabelText('Booking mode'), { target: { value: 'pending' } });
    fireEvent.click(dialog.getByRole('button', { name: 'Save pending reservation' }));
    expect(await screen.findByText(/Reservation #39 created.*Status: pending/)).toBeVisible();
    expect(calls.filter(c => c.method === 'POST').map(c => c.body)).toEqual([{ guest: guest.id, arrival: stay.arrival, departure: stay.departure, room_ids: [4, 7], confirm: false }]);
    expect(calls.filter(c => c.path === 'rooms/availability/').every(c => c.params.get('arrival') === stay.arrival && c.params.get('departure') === stay.departure)).toBe(true);
  });

  it('keeps its own claimed room on amendment, preserves a rejected selection and refreshes availability', async () => {
    let attempts = 0;
    const calls = openPage(<ReservationsPage />, ({ path, method }) => {
      if (path === 'rooms/availability/') return { data: pageOf(attempts ? [] : [otherRoom]) }; // Own confirmed claim is not returned.
      if (method === 'PATCH') return ++attempts === 1 ? { status: 409, data: { detail: 'Room T07 has a conflicting reservation.' } } : { data: stay };
      return { data: path === 'reservations/39/' ? stay : pageOf([stay]) };
    });
    fireEvent.click(await screen.findByRole('button', { name: 'Amend reservation #39' }));
    // The fresh detail request replaces its loading dialog with the populated editor.
    fireEvent.click(await screen.findByRole('checkbox', { name: /Room T07/ }));
    const dialog = within(screen.getByRole('dialog', { name: 'Amend reservation #39' }));
    fireEvent.click(dialog.getByRole('button', { name: 'Save amendment' }));
    expect(await dialog.findByRole('alert')).toHaveTextContent('Room T07 has a conflicting reservation.');
    expect(dialog.getByRole('list', { name: 'Selected rooms' })).toHaveTextContent('Room T04');
    expect(dialog.getByRole('list', { name: 'Selected rooms' })).toHaveTextContent('Room T07');
    expect(await dialog.findByText('No rooms match this availability search.')).toBeVisible();
    fireEvent.click(dialog.getByRole('button', { name: 'Remove room T07' }));
    fireEvent.change(dialog.getByLabelText('Departure date'), { target: { value: '2029-03-14' } });
    fireEvent.click(dialog.getByRole('button', { name: 'Save amendment' }));
    expect(await screen.findByText(/Reservation #39 amended/)).toBeVisible();
    expect(calls.filter(c => c.method === 'PATCH').map(c => c.body)).toEqual([
      { room_ids: [4, 7] }, { departure: '2029-03-14' },
    ]);
  });

  it('clears newly selected rooms when dates change and refuses to submit an invalid interval', async () => {
    const calls = openPage(<ReservationsPage />, ({ path }) => ({ data: pageOf<unknown>(path === 'guests/' ? [guest] : path === 'rooms/availability/' ? [room] : []) }));
    fireEvent.click(await screen.findByRole('button', { name: 'New reservation' }));
    const dialog = within(screen.getByRole('dialog', { name: 'New reservation' }));
    fireEvent.click(await dialog.findByRole('button', { name: /^Select Test Guest Alpha/ }));
    fireEvent.change(dialog.getByLabelText('Arrival date'), { target: { value: stay.arrival } });
    fireEvent.change(dialog.getByLabelText('Departure date'), { target: { value: stay.departure } });
    fireEvent.click(await dialog.findByRole('checkbox', { name: /Room T04/ }));
    fireEvent.change(dialog.getByLabelText('Departure date'), { target: { value: stay.arrival } });
    expect(dialog.queryByRole('button', { name: 'Remove room T04' })).not.toBeInTheDocument();
    fireEvent.click(dialog.getByRole('button', { name: 'Create confirmed reservation' }));
    await waitFor(() => expect(dialog.getByRole('alert')).toHaveTextContent(/Departure must be later/));
    expect(calls.filter(c => c.method === 'POST')).toHaveLength(0);
    expect(calls.filter(c => c.path === 'rooms/availability/')).toHaveLength(1);
  });
});
