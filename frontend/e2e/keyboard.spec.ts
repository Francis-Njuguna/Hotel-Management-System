import { randomBytes } from 'node:crypto';
import { expect, test, type Locator, type Page } from '@playwright/test';
import { apiReply, expectSignIn, jsonOK, signIn, submitSignIn, type Listing, type Staff } from './support';
import { origin } from './target';

// The operator must attest to the disposable API/database AND request this walk.
test.skip(process.env.HMS_E2E_DISPOSABLE !== '1' || process.env.HMS_E2E_KEYBOARD !== '1',
  'Requires both disposable-database and keyboard-walk opt-ins.');
test.use({ viewport: { width: 360, height: 800 } });

type Id = { id: number };
const amount = '25.00'; // Two fixture nights at KES 12.50; no external funds.

async function prepare(page: Page, actor: Staff) {
  for (const grant of ['staff.manage', 'guests.manage', 'rooms.manage', 'reservations.manage', 'billing.view', 'billing.manage', 'housekeeping.manage']) {
    expect(actor.capabilities.includes(grant), `Disposable setup requires ${grant}`).toBe(true);
  }
  const csrf = (await page.context().cookies(origin)).find(cookie => cookie.name === 'csrftoken')?.value;
  if (!csrf || new URL(page.url()).origin !== origin) throw new Error('Expected a same-origin staff session with CSRF protection.');
  const headers = { Origin: origin, 'X-CSRFToken': csrf, 'X-Hotel-Operator': String(actor.id) };
  async function fixture<T>(path: string, data?: object): Promise<T> {
    const response = await page.request.fetch(`${origin}/api/v1/${path}`, {
      method: data ? 'POST' : 'GET', data, headers, maxRedirects: 0, timeout: 10_000,
    }).catch(() => { throw new Error(`Fixture request failed: ${path}. Request details withheld.`); });
    try {
      if (!response.ok() || !response.headers()['content-type']?.includes('application/json')) {
        throw new Error(`Fixture ${path}: HTTP ${response.status()}. Request and response withheld.`);
      }
      return await response.json() as T;
    } finally { await response.dispose(); }
  }

  const tag = randomBytes(6).toString('hex');
  const username = `kb-cleaner-${tag}`, password = randomBytes(24).toString('base64url');
  const cleaner = await fixture<Id>('staff/', { username, password, email: `${username}@example.invalid`, role: 'Housekeeping Staff' });
  const guest = await fixture<Id & { reference: string }>('guests/', { reference: `KB-${tag}`, full_name: `Synthetic Guest ${tag}` });
  const room = (suffix: string) => fixture<Id & { number: string }>('rooms/', {
    number: `KB-${tag}-${suffix}`, category: 'Single', capacity: 1, nightly_rate: '12.50',
  });
  const lodging = await room('S'), cleaning = await room('C');
  const { date } = await fixture<{ date: string }>('dashboard/');
  expect(date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  const day = (offset: number) => new Date(Date.parse(`${date}T12:00:00Z`) + offset * 86_400_000).toISOString().slice(0, 10);
  const book = (arrival: string, departure: string, confirm: boolean) => fixture<Id>('reservations/', {
    guest: guest.id, room_ids: [lodging.id], arrival, departure, confirm,
  });
  const stay = await book(date, day(2), true);
  await fixture(`reservations/${stay.id}/check_in/`, {});
  const invoices = await fixture<Listing<Id & { balance: string }>>(`invoices/?reservation=${stay.id}&status=open`);
  expect(invoices.count).toBe(1);
  const invoice = invoices.results[0];
  expect(invoice.balance).toBe(amount);
  const pending = await book(day(2), day(3), false); // A later booking, not the stay with the open folio.
  const task = await fixture<Id & { assignee: number; status: string }>('cleaning-tasks/', { room: cleaning.id, assignee: cleaner.id });
  expect(task).toMatchObject({ assignee: cleaner.id, status: 'assigned' });
  return { guest, lodging, cleaning, stay, pending, invoice, task, cleaner, username, password, voucher: `SYNTHETIC-KB-${tag}` };
}

const button = (scope: Page | Locator, name: string) => scope.getByRole('button', { name, exact: true });

// Locators identify the goal, never move focus. Only the keyboard advances it.
async function tabTo(target: Locator) {
  await expect(target).toBeVisible();
  await expect(target).toBeEnabled();
  for (let n = 0; n < 32 && !await target.evaluate(el => el === document.activeElement); n++) {
    await target.page().keyboard.press('Tab');
  }
  await expect(target, 'Control must be reachable in at most 32 Tabs').toBeFocused({ timeout: 1_000 });
  await expect(target).toBeInViewport();
  expect(await target.evaluate(el => {
    const style = getComputedStyle(el);
    return el.matches(':focus-visible') && !['none', 'hidden'].includes(style.outlineStyle) && parseFloat(style.outlineWidth) > 0 &&
      !['transparent', 'rgba(0, 0, 0, 0)'].includes(style.outlineColor);
  }), 'The focused control must have a visible keyboard outline').toBe(true);
}
async function press(target: Locator, key = 'Enter') { await tabTo(target); await target.page().keyboard.press(key); }
async function typeAt(target: Locator, text: string) {
  await tabTo(target); await target.page().keyboard.type(text); await expect(target).toHaveValue(text);
}
async function menu(page: Page) {
  await press(button(page, 'Open navigation'));
  return page.getByRole('dialog', { name: 'Workspace menu' });
}
async function openModule(page: Page, name: 'Reservations' | 'Billing' | 'Housekeeping') {
  const drawer = await menu(page);
  await press(drawer.getByRole('link', { name, exact: true }));
  await expect(drawer).toBeHidden();
  await expect(page.getByRole('heading', { level: 1, name, exact: true })).toBeVisible();
}
async function fits(surface: Locator) {
  const [width, overflow] = await surface.page().evaluate(() => [innerWidth, document.documentElement.scrollWidth - document.documentElement.clientWidth]);
  expect(width, 'CSS viewport width').toBe(360);
  expect(overflow, 'Document-wide horizontal overflow').toBeLessThanOrEqual(0);
  expect(await surface.evaluate(el => el.scrollWidth - el.clientWidth), 'Horizontal overflow on the active surface').toBeLessThanOrEqual(0);
}

test('360 CSS px, keyboard: confirm a prepared booking, review and record tender, complete my assigned cleaning', async ({ page }) => {
  test.setTimeout(120_000);
  const staff = await signIn(page);
  const f = await prepare(page, staff); // No direct API reads/writes in the walkthrough below.

  await test.step('Find the pending booking, review its room and confirm; unpaid checkout on the other stay gives an alert', async () => {
    await openModule(page, 'Reservations');
    await typeAt(page.getByRole('searchbox', { name: 'Search reservations' }), f.guest.reference);
    const [search] = await Promise.all([apiReply(page, 'reservations', 'GET', f.guest.reference), page.keyboard.press('Enter')]);
    expect((await jsonOK<Listing<Id>>(search)).count).toBe(2);
    await expect(page.getByRole('navigation', { name: 'Reservations pages' })).toContainText('2 reservations');
    await fits(page.getByRole('region', { name: 'Reservation directory' }));
    const title = `Confirm reservation · #${f.pending.id}`;
    // Passively sample the transient loading status without delaying or replacing the real detail GET.
    const sawLoading = await page.evaluateHandle(() => {
      let seen = false;
      const observer = new MutationObserver(() => {
        seen ||= Array.from(document.querySelectorAll('dialog[open] [role="status"]')).some(el =>
          el.textContent === 'Checking current reservation…' && el.getClientRects().length > 0);
      });
      observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['open'] });
      return () => { observer.disconnect(); return seen; };
    });
    await press(button(page, title));
    const dialog = page.getByRole('dialog', { name: title, exact: true });
    await expect(dialog.getByText('Pending', { exact: true })).toBeVisible();
    expect(await sawLoading.evaluate(stop => stop()), 'Opening the booking exposed a distinct loading status').toBe(true);
    await sawLoading.dispose();
    await expect(dialog.getByRole('list', { name: 'Booked rooms and agreed rates' })).toContainText(`Room ${f.lodging.number}`);
    await fits(dialog);
    await press(button(dialog, 'Confirm reservation'));
    await expect(page.getByRole('status').filter({ hasText: `Reservation #${f.pending.id} updated` })).toContainText('Status: confirmed.');
    await expect(button(page, `Check in · #${f.pending.id}`)).toBeVisible();

    const checkout = `Check out · #${f.stay.id}`;
    await press(button(page, checkout));
    const unpaid = page.getByRole('dialog', { name: checkout, exact: true });
    const [conflict] = await Promise.all([apiReply(page, `reservations/${f.stay.id}/check_out`, 'POST'), press(button(unpaid, 'Check out'))]);
    expect(conflict.status()).toBe(409);
    await expect(unpaid.getByRole('alert')).toContainText(/outstanding folio balance/i);
    await page.keyboard.press('Escape');
    await expect(unpaid).toBeHidden();
  });

  await test.step('Review the counted synthetic cash voucher, acknowledge it, then identify its individual receipt', async () => {
    await openModule(page, 'Billing');
    await typeAt(page.getByLabel('Invoice number', { exact: true }), String(f.invoice.id));
    await page.keyboard.press('Enter');
    await expect(page.getByRole('region', { name: 'Invoice summary' })).toContainText(`Booking #${f.stay.id} ·`);
    await expect(page.getByText('No received payments on record for this invoice.', { exact: true })).toBeVisible();
    await press(button(page, 'Record payment'));
    const entry = page.getByRole('form', { name: 'Record received payment' });
    const method = entry.getByRole('combobox', { name: 'Payment method' });
    await press(method, 'ArrowDown'); await expect(method).toHaveValue('cash');
    await typeAt(entry.getByLabel('Amount received (KES)', { exact: true }), amount);
    await typeAt(entry.getByLabel('Payment reference', { exact: true }), f.voucher);
    await fits(entry);
    await press(button(entry, 'Review payment'));
    const review = page.getByRole('form', { name: 'Review payment' });
    for (const text of [`KES ${amount}`, 'Cash', f.voucher]) await expect(review.getByText(text, { exact: true })).toBeVisible();
    await fits(review);
    const confirm = button(review, 'Confirm payment');
    await expect(confirm).toBeDisabled();
    const acknowledgment = review.getByRole('checkbox', { name: /received and counted this cash/i });
    await press(acknowledgment, 'Space'); await expect(acknowledgment).toBeChecked();
    const [recorded] = await Promise.all([apiReply(page, `invoices/${f.invoice.id}/payments`, 'POST'), press(confirm)]);
    expect(recorded.status()).toBe(201);
    const receipt = page.getByRole('article', { name: 'Individual payment receipt' });
    await expect(page.getByRole('status').filter({ hasText: 'Payment on record.' })).toBeVisible();
    await expect(receipt.getByRole('heading', { name: `Receipt ${(await recorded.json()).receipt_number}`, exact: true })).toBeVisible();
    for (const text of [`#${f.invoice.id}`, `KES ${amount}`, f.voucher, `Staff #${staff.id}`]) await expect(receipt.getByText(text, { exact: true })).toBeVisible();
    await fits(receipt);
  });

  await test.step('As the assigned housekeeper, start and complete the task; completion is not inspection', async () => {
    await press(button(await menu(page), 'Sign out'));
    await expectSignIn(page);
    const { user } = await jsonOK<{ user: Staff }>(await submitSignIn(page, f.username, f.password));
    expect(user.id).toBe(f.cleaner.id); expect(user.roles).toEqual(['Housekeeping Staff']);
    await openModule(page, 'Housekeeping');
    const queue = page.getByRole('region', { name: 'Cleaning tasks' });
    await expect(queue.getByRole('heading', { name: 'My cleaning tasks' })).toBeVisible();
    const card = queue.getByRole('article', { name: `Room ${f.cleaning.number}, cleaning task ${f.task.id}`, exact: true });
    await expect(card.getByText('Assigned', { exact: true })).toBeVisible();
    await expect(card.getByText(f.username, { exact: true })).toBeVisible();
    for (const [action, status] of [['Start cleaning', 'In progress'], ['Complete cleaning', 'Completed']]) {
      await press(button(card, action));
      await expect(queue.getByRole('status').filter({ hasText: `task #${f.task.id} is now ${status.toLowerCase()}.` })).toBeVisible();
      await expect(card.getByText(status, { exact: true })).toBeVisible();
      await fits(card);
    }
    await expect(card.getByText(/Manager inspection is still required/)).toBeVisible();
  });
});
