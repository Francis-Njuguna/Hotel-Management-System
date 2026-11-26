import { act, fireEvent, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BillingPage } from '../index';
import type { Invoice, Payment } from '../model';
import { mountOffice, paged } from './transport';

// Synthetic records only; no funds are sent, received or verified by these tests.
const invoice: Invoice = {
  id: 41, reservation: 15, created_at: '2026-02-03T09:00:00Z', closed_at: null,
  total: '4850.25', paid: '0.00', balance: '4850.25', payments: [],
  items: [{ id: 2, description: 'Test room nights', quantity: 2, unit_price: '2000.00', line_total: '4000.00', source_key: 'room:2' },
    { id: 3, description: 'Test room service', quantity: 1, unit_price: '850.25', line_total: '850.25', source_key: 'order:3' }],
};
const payment: Payment = {
  id: 17, amount: '2000.00', invoice: 41, method: 'mobile_money', reference: 'TEST-MOBILE-17',
  received_by: 8, receipt_number: 'TEST-RCPT-17', created_at: '2026-02-03T12:12:00Z',
};
const accountant = ['billing.view', 'billing.manage'];
const button = (name: string) => screen.getByRole('button', { name });
const fill = (name: string, value: string) => fireEvent.change(screen.getByLabelText(name, { exact: true }), { target: { value } });
async function openInvoice(id = 41) {
  fireEvent.click(await screen.findByRole('button', { name: `Invoice #${id}` }));
  await screen.findByRole('table', { name: 'Charge details' });
}

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('BillingPage', () => {
  it('requests real pages and itemized invoice details and retains the register page on return', async () => {
    const second = { ...invoice, id: 42, reservation: null };
    const calls = mountOffice(<BillingPage />, accountant, ({ path }) => {
      if (path === 'invoices/?page=1') return paged([invoice], { count: 26, next: '?page=2' });
      if (path === 'invoices/?page=2') return paged([second], { count: 26, previous: '?page=1' });
      if (path === 'invoices/42/') return second;
      throw new Error(`Unexpected path ${path}`);
    });
    await screen.findByRole('button', { name: 'Invoice #41' });
    expect(button('Previous')).toBeDisabled();
    fireEvent.click(button('Next'));
    await openInvoice(42);
    expect(screen.getByText('Test room service')).toBeVisible();
    expect(screen.getByText('room:2')).toBeVisible();
    expect(screen.getByText('KES 4,000.00')).toBeVisible();
    expect(screen.getByText(/no received payments on record/i)).toBeVisible();
    fireEvent.click(button('Back to invoices'));
    expect(await screen.findByText('Page 2 · 26 invoices')).toBeVisible();
    expect(button('Next')).toBeDisabled();
    expect(calls.every(call => call.method === 'GET')).toBe(true);
  });

  it('looks up only the specified booking for read-only reception; no posting or hotel-wide registers', async () => {
    const calls = mountOffice(<BillingPage />, ['billing.view'], ({ path }) => {
      if (path === 'invoices/?page=1&reservation=15') return paged([invoice]);
      if (path === 'invoices/41/') return invoice;
      throw new Error(`Unexpected path ${path}`);
    });
    await screen.findByRole('button', { name: 'Find folio' });
    expect(calls.map(c => c.path)).toEqual(['auth/me/']);
    fill('Booking number', '15'); fireEvent.click(button('Find folio')); await openInvoice();
    expect(screen.getByText(/read-only access/i)).toBeVisible();
    expect(screen.queryByRole('button', { name: /add charge|record payment/i })).not.toBeInTheDocument();
    expect(calls.map(c => c.path)).toEqual(['auth/me/', 'invoices/?page=1&reservation=15', 'invoices/41/']);
    expect(calls.every(call => call.method === 'GET')).toBe(true);
  });

  it('does not load billing records without billing.view', async () => {
    const calls = mountOffice(<BillingPage />, [], () => { throw new Error('Unpermitted read'); });
    expect(await screen.findByText(/do not have access to billing/i)).toBeVisible();
    expect(calls.map(c => c.path)).toEqual(['auth/me/']);
  });

  it('shows a failed collection as an error, then shows the empty state only after a successful retry', async () => {
    let first = true;
    mountOffice(<BillingPage />, accountant, () => {
      if (first) { first = false; return new Response(JSON.stringify({ detail: 'Test service unavailable' }),
        { status: 503, headers: { 'Content-Type': 'application/json' } }); }
      return paged([]);
    });
    expect(await screen.findByRole('alert')).toHaveTextContent('Test service unavailable');
    expect(screen.queryByText('No invoices to display.')).not.toBeInTheDocument();
    fireEvent.click(button('Retry'));
    expect(await screen.findByText('No invoices to display.')).toBeVisible();
  });

  it('posts only reviewed charge inputs, preserving cents and re-reading invoice totals', async () => {
    const line = { id: 9, invoice: 41, description: 'Test laundry', quantity: 2, unit_price: '85.20', line_total: '170.40', source_key: 'extra:41:TEST-SLIP-9' };
    let current = invoice;
    const calls = mountOffice(<BillingPage />, accountant, ({ path, method }) => {
      if (path === 'invoices/?page=1') return paged([current]);
      if (path === 'invoices/41/') return current;
      if (path === 'invoices/41/charges/' && method === 'POST') {
        current = { ...invoice, items: [...invoice.items, line], total: '5020.65', balance: '5020.65' }; return line;
      }
      throw new Error(`Unexpected path ${path}`);
    });
    await openInvoice(); fireEvent.click(button('Add charge'));
    fill('Description', 'Test laundry'); fill('Quantity', '2'); fill('Source reference', 'TEST-SLIP-9'); fill('Unit price (KES)', '85.201');
    fireEvent.click(button('Review charge'));
    expect(screen.getByRole('alert')).toHaveTextContent(/two decimal places/);
    fill('Unit price (KES)', '85.2'); fireEvent.click(button('Review charge'));
    expect(calls.filter(c => c.method === 'POST')).toHaveLength(0);
    fireEvent.click(button('Confirm charge'));
    const charges = await screen.findByRole('table', { name: 'Charge details' });
    expect(within(charges).getByText('Test laundry')).toBeVisible();
    expect(within(charges).getByText('KES 85.20')).toBeVisible();
    expect(screen.getAllByText('KES 5,020.65')).toHaveLength(2);
    expect(calls.filter(c => c.method === 'POST')).toEqual([{ path: 'invoices/41/charges/', method: 'POST',
      body: { quantity: 2, description: 'Test laundry', unit_price: '85.20', reference: 'TEST-SLIP-9' } }]);
  });

  it('requires verified receipt of funds, locks double submissions, and retries the identical tender after a lost reply', async () => {
    let lostReply: (() => void) | undefined;
    let recorded = false;
    const calls = mountOffice(<BillingPage />, accountant, ({ path, method }) => {
      if (path === 'invoices/?page=1') return paged([invoice]);
      if (path === 'invoices/41/') return recorded ? { ...invoice, paid: '2000.00', balance: '2850.25', payments: [payment] } : invoice;
      if (path === 'invoices/41/payments/' && method === 'POST') {
        if (recorded) return payment;
        recorded = true;
        return new Promise((_resolve, reject) => { lostReply = () => reject(new TypeError('Test connection lost')); });
      }
      if (path === 'payments/17/') return payment;
      throw new Error(`Unexpected path ${path}`);
    });
    const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    await openInvoice(); fireEvent.click(button('Record payment'));
    fill('Payment method', 'mobile_money'); fill('Payment reference', 'TEST-MOBILE-17');
    fill('Amount received (KES)', '4850.26'); fireEvent.click(button('Review payment'));
    expect(screen.getByRole('alert')).toHaveTextContent(/cannot exceed/);
    fill('Amount received (KES)', '2000.0'); fireEvent.click(button('Review payment'));
    expect(button('Confirm payment')).toBeDisabled();
    expect(calls.filter(c => c.method === 'POST')).toHaveLength(0);
    fireEvent.click(screen.getByRole('checkbox', { name: /verified this received amount/ }));
    fireEvent.click(button('Confirm payment'));
    fireEvent.submit(screen.getByRole('form', { name: 'Review payment' }));
    expect(calls.filter(c => c.method === 'POST')).toHaveLength(1);
    await act(async () => { lostReply!(); });
    expect(await screen.findByRole('alert')).toHaveTextContent(/do not use a new reference/i);
    expect(screen.queryByRole('button', { name: 'Edit entry' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Print receipt' })).not.toBeInTheDocument();
    fireEvent.click(button('Retry same payment'));
    const receipt = await screen.findByRole('article', { name: 'Individual payment receipt' });
    const expected = { path: 'invoices/41/payments/', method: 'POST', body: { amount: '2000.00', method: 'mobile_money', reference: 'TEST-MOBILE-17' } };
    expect(calls.filter(c => c.method === 'POST')).toEqual([expected, expected]);
    expect(within(receipt).getByText('Receipt TEST-RCPT-17')).toBeVisible();
    expect(receipt).toHaveTextContent('KES 2,000.00');
    expect(receipt).not.toHaveTextContent(/4,850.25|2,850.25|paid in full|settled/i);
    expect(print).not.toHaveBeenCalled(); fireEvent.click(button('Print receipt')); expect(print).toHaveBeenCalledOnce();
    expect(document.body.querySelector(':scope > .office-print-copy')).toHaveTextContent('TEST-MOBILE-17');
    fireEvent.click(button('Back to invoice #41'));
    expect(await screen.findByText('KES 2,850.25')).toBeVisible();
    expect(document.body.querySelector('.office-print-copy')).toBeNull();
  });

  it('refuses to print a payment returned for a different invoice', async () => {
    mountOffice(<BillingPage />, accountant, ({ path }) => {
      if (path === 'invoices/?page=1') return paged([invoice]);
      if (path === 'invoices/41/') return { ...invoice, payments: [payment] };
      if (path === 'payments/17/') return { ...payment, invoice: 99 };
      throw new Error(`Unexpected path ${path}`);
    });
    await openInvoice(); fireEvent.click(button(payment.receipt_number));
    expect(await screen.findByRole('alert')).toHaveTextContent('No printable receipt');
    expect(screen.queryByRole('button', { name: 'Print receipt' })).not.toBeInTheDocument();
  });

  it('pages long tender histories through the selected invoice, not the hotel-wide payments register', async () => {
    const tenders = Array.from({ length: 26 }, (_, index) => ({ ...payment, id: 40 + index, amount: '1.00',
      reference: `TEST-SPLIT-${index}`, receipt_number: `TEST-RECEIPT-${index}` }));
    const detail = { ...invoice, paid: '26.00', balance: '4824.25', payments: tenders };
    const calls = mountOffice(<BillingPage />, accountant, ({ path }) => {
      if (path === 'invoices/?page=1') return paged([detail]);
      if (path === 'invoices/41/') return detail;
      if (path === 'invoices/41/payments/?page=1&page_size=25') return paged(tenders.slice(0, 25), { count: 26, next: '?page=2' });
      if (path === 'invoices/41/payments/?page=2&page_size=25') return paged(tenders.slice(25), { count: 26, previous: '?page=1' });
      throw new Error(`Unexpected path ${path}`);
    });
    await openInvoice();
    await screen.findByRole('navigation', { name: 'Payments pagination' });
    expect(screen.queryByRole('button', { name: 'TEST-RECEIPT-25' })).not.toBeInTheDocument();
    fireEvent.click(button('Next'));
    expect(await screen.findByRole('button', { name: 'TEST-RECEIPT-25' })).toBeVisible();
    expect(calls.some(call => call.path.startsWith('payments/'))).toBe(false);
  });
});
