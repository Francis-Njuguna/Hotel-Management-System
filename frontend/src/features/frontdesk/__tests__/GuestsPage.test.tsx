import { fireEvent, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { GuestsPage } from '../GuestsPage';
import { guest, openPage, pageOf, stay } from './harness';

describe('Guest directory', () => {
  it('paginates on the server and distinguishes a failed search from an empty result', async () => {
    let attempts = 0;
    const calls = openPage(<GuestsPage />, ({ path, params }) => {
      if (path !== 'guests/') throw new Error(`Unexpected ${path}`);
      if (params.get('search') === 'absent') return ++attempts === 1
        ? { status: 503, data: { detail: 'Directory temporarily unavailable.' } } : { data: pageOf([]) };
      return params.get('page') === '2' ? { data: pageOf([{ ...guest, id: 13, full_name: 'Test Guest Beta' }], { count: 21, previous: '?page=1' }) }
        : { data: pageOf([guest], { count: 21, next: '?page=2' }) };
    });
    expect(await screen.findByText(guest.full_name)).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Next page of guests' }));
    expect(await screen.findByText('Test Guest Beta')).toBeVisible();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search guests' }), { target: { value: 'absent' } });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Directory temporarily unavailable.');
    expect(screen.queryByText(/No guests match/)).not.toBeInTheDocument();
    expect(screen.queryByText('Test Guest Beta')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText(/No guests match/)).toBeVisible();
    expect(calls.filter(c => c.params.get('search') === 'absent').map(c => c.params.get('page'))).toEqual(['1', '1']);
  });

  it('keeps a rejected registration draft, then registers and edits only the changed field', async () => {
    let stored = false;
    let attempts = 0;
    const calls = openPage(<GuestsPage />, ({ path, method }) => {
      if (method === 'GET') return { data: pageOf(stored ? [guest] : []) };
      if (method === 'POST' && ++attempts === 1) return { status: 400, data: { email: ['That email is already registered.'] } };
      if (path === `guests/${guest.id}/` && method === 'PATCH') return { data: { ...guest, phone: 'TEST-012' } };
      stored = true; return { data: guest, status: 201 };
    });
    fireEvent.click(await screen.findByRole('button', { name: 'Register guest' }));
    let dialog = within(screen.getByRole('dialog', { name: 'Register guest' }));
    fireEvent.change(dialog.getByLabelText(/Full name/), { target: { value: guest.full_name } });
    fireEvent.change(dialog.getByLabelText('Email address'), { target: { value: 'used@example.test' } });
    fireEvent.click(dialog.getByRole('button', { name: 'Register guest' }));
    expect(await dialog.findByRole('alert')).toHaveTextContent('email: That email is already registered.');
    expect(dialog.getByLabelText(/Full name/)).toHaveValue(guest.full_name);
    fireEvent.change(dialog.getByLabelText('Email address'), { target: { value: guest.email } });
    fireEvent.click(dialog.getByRole('button', { name: 'Register guest' }));
    expect(await screen.findByText(`${guest.full_name} (${guest.reference}) registered.`)).toBeVisible();
    expect(calls.filter(c => c.method === 'POST').at(-1)?.body).toEqual({ full_name: guest.full_name, email: guest.email, phone: '' });
    fireEvent.click(await screen.findByRole('button', { name: /^Edit Test Guest Alpha/ }));
    dialog = within(screen.getByRole('dialog', { name: 'Edit guest' }));
    fireEvent.change(dialog.getByLabelText('Phone number'), { target: { value: 'TEST-012' } });
    fireEvent.click(dialog.getByRole('button', { name: 'Save guest changes' }));
    expect(await screen.findByText(`${guest.full_name} (${guest.reference}) updated.`)).toBeVisible();
    expect(calls.find(c => c.method === 'PATCH')?.body).toEqual({ phone: 'TEST-012' });
  });

  it('shows guest history without editing or rendering payment information outside the grant', async () => {
    openPage(<GuestsPage />, ({ path }) => path.endsWith('/history/') ? { data: {
      reservations: [stay], payments: [{ id: 14, amount: '10.00', created_at: '2029-03-10T11:00:00Z', receipt_number: 'TEST-RECEIPT' }],
    } } : { data: pageOf([guest]) }, ['guests.view']);
    fireEvent.click(await screen.findByRole('button', { name: /^History for Test Guest Alpha/ }));
    const dialog = within(screen.getByRole('dialog', { name: 'Guest history' }));
    expect(await dialog.findByText('Reservation #39')).toBeVisible();
    expect(dialog.queryByText('Payments')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Register guest' })).not.toBeInTheDocument();
  });

  it('distinguishes actual arrival and departure from booked nights and includes authorized receipt history', async () => {
    openPage(<GuestsPage />, ({ path }) => path.endsWith('/history/') ? { data: {
      reservations: [{ ...stay, status: 'checked_out', checked_in_at: '2029-03-10T07:30:00Z', checked_out_at: '2029-03-11T05:15:00Z' }],
      payments: [{ id: 14, amount: '4901.00', receipt_number: 'TEST-014', created_at: '2029-03-10T09:00:00Z' }],
    } } : { data: pageOf([guest]) });
    fireEvent.click(await screen.findByRole('button', { name: /^History for Test Guest Alpha/ }));
    const dialog = within(screen.getByRole('dialog', { name: 'Guest history' }));
    expect(await dialog.findByText(/Actual check-in:.*10:30/)).toBeVisible();
    expect(dialog.getByText(/Actual checkout:.*08:15/)).toBeVisible();
    expect(dialog.getByRole('link', { name: 'Reservation #39' })).toHaveAttribute('href', '/reservations?reservation=39');
    expect(dialog.getByText('Receipt TEST-014')).toBeVisible();
    expect(dialog.getByText('KES 4,901.00')).toBeVisible();
  });
});
