import { randomUUID } from 'node:crypto';
import { expect, test, type Locator, type Page } from '@playwright/test';
import { apiReply, navLink, signIn, type Listing } from './support';

// File-wide, before any hooks, fixtures, login or catalog writes. This environment
// flag is the operator's attestation that the *served API* points to an isolated
// synthetic PostgreSQL clone. Neither a loopback address nor a demo account proves it.
test.skip(process.env.HMS_E2E_DISPOSABLE !== '1', 'Write journey: explicit disposable PostgreSQL clone opt-in required.');

type Guest = { id: number; reference: string; full_name: string };
type Room = { id: number; number: string; nightly_rate: string; is_active: boolean; occupied: boolean; maintenance: boolean; cleanliness: string };
type Stay = { id: number; status: string; guest: number; arrival: string; departure: string;
  rooms: Pick<Room, 'id' | 'number' | 'nightly_rate'>[]; checked_in_at: string | null; checked_out_at: string | null;
  events: { status: string }[] };
type Payment = { id: number; invoice: number; amount: string; method: string; reference: string; received_by: number; receipt_number: string };
type Folio = { id: number; reservation: number; closed_at: string | null; total: string; paid: string; balance: string;
  items: { id: number; quantity: number; unit_price: string; line_total: string }[]; payments: Payment[] };
type Task = { id: number; room: number; room_number: string; status: string; assignee: number | null };

// All write requests come from real UI controls. Only ordinary scoped GETs are
// issued here, with the browser's own staff session; never use an admin DB handle.
async function read<T>(page: Page, path: string): Promise<T> {
  const res = await page.request.get(`/api/v1/${path}`, { maxRedirects: 0 });
  try {
    expect(res.status(), `Authenticated read: ${path.split('?')[0]}`).toBe(200);
    expect(res.headers()['content-type']).toMatch(/application\/json/i);
    return await res.json() as T;
  } finally { await res.dispose(); }
}

async function clickPost<T>(page: Page, button: Locator, path: string, status: number): Promise<T> {
  const [res] = await Promise.all([apiReply(page, path, 'POST'), button.click()]);
  expect(res.status(), `Staff command: ${path}`).toBe(status);
  expect(res.headers()['content-type']).toMatch(/application\/json/i);
  return await res.json() as T;
}

function stayRow(page: Page, id: number) {
  return page.getByRole('table', { name: 'Reservations and stay actions' }).getByRole('row')
    .filter({ has: page.getByText(`Reservation #${id}`, { exact: true }) });
}

async function openTransition(page: Page, id: number, action: 'Check in' | 'Check out') {
  const title = `${action} · #${id}`;
  await stayRow(page, id).getByRole('button', { name: title, exact: true }).click();
  return page.getByRole('dialog', { name: title, exact: true });
}

function kes(decimal: string) {
  const [whole, cents] = decimal.split('.');
  return `KES ${BigInt(whole).toLocaleString('en-GB')}.${cents}`;
}

async function expectInvoiceUI(page: Page, booking: number, charged: string, paid: string, balance: string) {
  const summary = page.getByRole('region', { name: 'Invoice summary' });
  await expect(summary).toContainText(`Booking #${booking} ·`);
  for (const [label, amount] of [['Charged', charged], ['Received', paid], ['Balance due', balance]]) {
    const field = summary.locator('dl > div').filter({ has: page.getByText(label, { exact: true }) });
    await expect(field.getByRole('definition')).toHaveText(kes(amount));
  }
}

test('disposable stay: admit, reject unpaid checkout, record one verified tender, close the stay and open turnover', async ({ page }) => {
  test.setTimeout(120_000);
  const staff = await signIn(page);
  for (const grant of ['reservations.manage', 'billing.view', 'billing.manage', 'housekeeping.view', 'housekeeping.manage']) {
    expect(staff.capabilities.includes(grant), `Disposable clone needs a demo manager/administrator with ${grant}`).toBe(true);
  }

  // An additional fixture interlock, not a substitute for verifying the clone.
  // Dates come from the hotel's clock. Use only seed_demo's synthetic guest and a
  // positively priced, available, inspected demo room, never arbitrary list rows.
  const [{ date: arrival }, guests] = await Promise.all([
    read<{ date: string }>(page, 'dashboard/'), read<Listing<Guest>>(page, 'guests/?search=DEMO-GUEST'),
  ]);
  const guest = guests.results.find(g => g.reference === 'DEMO-GUEST' && g.full_name === 'Demo Guest');
  if (!guest) throw new Error('Expected the synthetic seed_demo guest in the disposable clone. No booking made.');
  expect(arrival).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  const end = new Date(`${arrival}T12:00:00Z`);
  end.setUTCDate(end.getUTCDate() + 1);
  const departure = end.toISOString().slice(0, 10);
  const availability = await read<Listing<Room>>(page, `rooms/availability/?arrival=${arrival}&departure=${departure}&search=Demo%20catalog&page_size=100`);
  const room = availability.results.find(r => /^D(?:10[1-3]|20[1-3])$/.test(r.number) && r.is_active && !r.occupied && !r.maintenance &&
    r.cleanliness === 'inspected' && /^\d+\.\d{2}$/.test(r.nightly_rate) && BigInt(r.nightly_rate.replace('.', '')) > 0n);
  if (!room) throw new Error('Expected an available, inspected, positive-rate seed_demo room in the clone. No booking made.');
  const price = room.nightly_rate; // One contracted night. Compare exact KES strings, including on early departure.
  const tasksPath = `cleaning-tasks/?room=${room.id}&page_size=100`;
  const baseline = await read<Listing<Task>>(page, tasksPath); // Historical inspected tasks are allowed.
  const previousTasks = new Set(baseline.results.map(task => task.id));

  const booking = await test.step('Book the selected guest and room in the reservation form', async () => {
    await navLink(page, 'Guests').click();
    const directory = page.getByRole('region', { name: 'Guest directory' });
    await directory.getByRole('searchbox', { name: 'Search guests' }).fill(guest.reference);
    await directory.getByRole('button', { name: 'Search', exact: true }).click();
    await directory.getByRole('link', { name: `Book a stay for ${guest.full_name}, ${guest.reference}`, exact: true }).click();
    const form = page.getByRole('dialog', { name: 'New reservation' });
    await expect(form.getByText(guest.full_name, { exact: true })).toBeVisible();
    await form.getByLabel('Arrival date', { exact: true }).fill(arrival);
    await form.getByLabel('Departure date', { exact: true }).fill(departure);
    const search = form.getByRole('searchbox', { name: 'Search available rooms' });
    await search.fill(room.number);
    await search.press('Enter');
    await form.getByRole('checkbox', { name: new RegExp(`^Room ${room.number} ·`) }).check();
    await expect(form.getByRole('list', { name: 'Selected rooms' })).toContainText(kes(price));
    await form.getByLabel('Booking mode').selectOption('confirmed');
    const stay = await clickPost<Stay>(page, form.getByRole('button', { name: 'Create confirmed reservation' }), 'reservations', 201);
    expect(stay).toMatchObject({ guest: guest.id, arrival, departure, status: 'confirmed', checked_in_at: null, checked_out_at: null });
    expect(stay.rooms).toEqual([{ id: room.id, number: room.number, nightly_rate: price }]);
    await expect(stayRow(page, stay.id).getByText('Confirmed', { exact: true })).toBeVisible();
    expect((await read<Listing<Folio>>(page, `invoices/?reservation=${stay.id}`)).count, 'Booking alone must not open a folio').toBe(0);
    return stay;
  });

  const stayPath = `reservations/${booking.id}`;
  const folio = await test.step('Check in; one open folio charges the agreed night, not a payment', async () => {
    const dialog = await openTransition(page, booking.id, 'Check in');
    const admitted = await clickPost<Stay>(page, dialog.getByRole('button', { name: 'Check in', exact: true }), `${stayPath}/check_in`, 200);
    expect(admitted).toMatchObject({ id: booking.id, status: 'checked_in', checked_out_at: null });
    expect(admitted.checked_in_at).toEqual(expect.any(String));
    await expect(stayRow(page, booking.id).getByText('Checked in', { exact: true })).toBeVisible();
    const [invoices, occupied] = await Promise.all([
      read<Listing<Folio>>(page, `invoices/?reservation=${booking.id}`), read<Room>(page, `rooms/${room.id}/`),
    ]);
    expect(occupied).toMatchObject({ id: room.id, occupied: true, cleanliness: 'inspected' });
    expect(invoices.count).toBe(1);
    const invoice = await read<Folio>(page, `invoices/${invoices.results[0].id}/`);
    expect(invoice).toMatchObject({ reservation: booking.id, closed_at: null, total: price, paid: '0.00', balance: price, payments: [] });
    expect(invoice.items).toHaveLength(1);
    expect(invoice.items[0]).toMatchObject({ quantity: 1, unit_price: price, line_total: price });
    return invoice;
  });

  const invoicePath = `invoices/${folio.id}`;
  await test.step('Unpaid checkout conflicts without closing the stay, posting money or opening turnover', async () => {
    const dialog = await openTransition(page, booking.id, 'Check out');
    const denial = await clickPost<{ detail: string }>(page, dialog.getByRole('button', { name: 'Check out', exact: true }), `${stayPath}/check_out`, 409);
    expect(denial.detail).toMatch(/outstanding folio balance/i);
    await expect(dialog.getByRole('alert')).toContainText(denial.detail);
    const [stay, invoice, currentRoom, tasks] = await Promise.all([
      read<Stay>(page, `${stayPath}/`), read<Folio>(page, `${invoicePath}/`),
      read<Room>(page, `rooms/${room.id}/`), read<Listing<Task>>(page, tasksPath),
    ]);
    expect(stay).toMatchObject({ id: booking.id, status: 'checked_in', checked_out_at: null });
    expect(stay.events.map(e => e.status)).toEqual(['confirmed', 'checked_in']);
    expect(invoice).toEqual(folio); // Same ledger snapshot, not only the same balance.
    expect(currentRoom).toMatchObject({ occupied: true, cleanliness: 'inspected' });
    expect(tasks).toEqual(baseline); // Rejection cannot add *any* task or change an existing task.
    await dialog.getByRole('button', { name: 'Go back' }).click();
    await expect(stayRow(page, booking.id).getByText('Checked in', { exact: true })).toBeVisible();
  });

  const nav = page.getByRole('navigation', { name: 'Main navigation' });
  const payment = await test.step('Review a synthetic counted-cash voucher, acknowledge it and reconcile the receipt', async () => {
    // In-memory evidence for this clone only. Not a gateway call, real till entry or card/bank reference.
    const voucher = { method: 'cash', amount: price, reference: `SYNTHETIC-E2E-VOUCHER-${randomUUID()}` };
    await nav.getByRole('link', { name: 'Billing', exact: true }).click();
    const lookup = page.getByRole('region', { name: 'Invoice register' });
    await lookup.getByLabel('Invoice number', { exact: true }).fill(String(folio.id));
    await lookup.getByRole('button', { name: 'Find invoice' }).click();
    await expectInvoiceUI(page, booking.id, price, '0.00', price);
    await page.getByRole('button', { name: 'Record payment', exact: true }).click();
    const entry = page.getByRole('form', { name: 'Record received payment' });
    await entry.getByLabel('Payment method').selectOption(voucher.method);
    await entry.getByLabel('Amount received (KES)', { exact: true }).fill(voucher.amount);
    await entry.getByLabel('Payment reference').fill(voucher.reference);
    await entry.getByRole('button', { name: 'Review payment' }).click();
    const review = page.getByRole('form', { name: 'Review payment' });
    await expect(review.getByText(kes(voucher.amount), { exact: true })).toBeVisible();
    await expect(review.getByText('Cash', { exact: true })).toBeVisible();
    await expect(review.getByText(voucher.reference, { exact: true })).toBeVisible();
    const confirm = review.getByRole('button', { name: 'Confirm payment' });
    await expect(confirm).toBeDisabled();
    expect((await read<Folio>(page, `${invoicePath}/`)).payments, 'Review alone must not post tender').toHaveLength(0);
    await review.getByRole('checkbox', { name: /received and counted this cash/i }).check();
    const received = await clickPost<Payment>(page, confirm, `${invoicePath}/payments`, 201);
    expect(received).toMatchObject({ ...voucher, invoice: folio.id, received_by: staff.id });
    expect(received.receipt_number).toMatch(/\S/);
    const receipt = page.getByRole('article', { name: 'Individual payment receipt' });
    await expect(receipt.getByRole('heading', { name: `Receipt ${received.receipt_number}`, exact: true })).toBeVisible();
    for (const text of [voucher.reference, kes(voucher.amount), 'Cash', `#${folio.id}`, `Staff #${staff.id}`]) {
      await expect(receipt.getByText(text, { exact: true })).toBeVisible();
    }
    await page.getByRole('button', { name: `Back to invoice #${folio.id}`, exact: true }).click();
    await expectInvoiceUI(page, booking.id, price, price, '0.00');
    await expect(page.getByRole('region', { name: 'Invoice summary' }).getByText('Open', { exact: true })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Payments received' }).getByRole('button', { name: received.receipt_number })).toBeVisible();
    const settled = await read<Folio>(page, `${invoicePath}/`);
    expect(settled).toMatchObject({ reservation: booking.id, closed_at: null, total: price, paid: price, balance: '0.00' });
    expect(settled.payments).toEqual([received]); // Settlement is not checkout.
    return received;
  });

  await test.step('Check out; verify the closed folio, released occupancy and a new pending task for that same room', async () => {
    await navLink(page, 'Reservations').click();
    const dialog = await openTransition(page, booking.id, 'Check out');
    const result = await clickPost<Stay>(page, dialog.getByRole('button', { name: 'Check out', exact: true }), `${stayPath}/check_out`, 200);
    expect(result).toMatchObject({ id: booking.id, status: 'checked_out' });
    await expect(stayRow(page, booking.id).getByText('Checked out', { exact: true })).toBeVisible();
    const [stay, closed, roomNow, tasks] = await Promise.all([
      read<Stay>(page, `${stayPath}/`), read<Folio>(page, `${invoicePath}/`),
      read<Room>(page, `rooms/${room.id}/`), read<Listing<Task>>(page, tasksPath),
    ]);
    expect(stay).toMatchObject({ id: booking.id, guest: guest.id, status: 'checked_out', arrival, departure });
    expect(Date.parse(stay.checked_out_at ?? '')).toBeGreaterThanOrEqual(Date.parse(stay.checked_in_at ?? ''));
    expect(stay.events.map(e => e.status)).toEqual(['confirmed', 'checked_in', 'checked_out']);
    expect(closed).toMatchObject({ id: folio.id, reservation: booking.id, closed_at: expect.any(String), total: price, paid: price, balance: '0.00' });
    expect(closed.items).toEqual(folio.items);
    expect(closed.payments).toEqual([payment]); // Exactly the tender acknowledged on screen; checkout did not collect again.
    expect(roomNow).toMatchObject({ id: room.id, occupied: false, cleanliness: 'dirty' });
    expect(tasks.count).toBe(baseline.count + 1);
    const added = tasks.results.filter(t => !previousTasks.has(t.id)); // Newest first, scoped to this room.
    expect(added).toHaveLength(1);
    const task = added[0];
    expect(task).toMatchObject({ room: room.id, room_number: room.number, status: 'pending', assignee: null });

    await navLink(page, 'Rooms').click();
    const filters = page.getByRole('region', { name: 'Room filters' });
    await filters.getByRole('searchbox', { name: 'Search rooms' }).fill(room.number);
    await filters.getByRole('button', { name: 'Apply filters' }).click();
    const condition = page.getByRole('article', { name: `Room ${room.number}`, exact: true }).getByRole('list', { name: 'Current room condition' });
    await expect(condition.getByText('Unoccupied now', { exact: true })).toBeVisible();
    await expect(condition.getByText('Needs cleaning', { exact: true })).toBeVisible();
    await nav.getByRole('link', { name: /^Housekeeping/ }).click();
    const card = page.getByRole('region', { name: 'Cleaning tasks' }).getByRole('article', { name: `Room ${room.number}, cleaning task ${task.id}`, exact: true });
    await expect(card.getByText('Pending', { exact: true })).toBeVisible();
    await expect(card.getByText('Unassigned', { exact: true })).toBeVisible();
  });
});
