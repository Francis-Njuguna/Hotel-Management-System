import { randomUUID } from 'node:crypto';
import { expect, test, type Locator } from '@playwright/test';
import { apiReply, expectListDenied, expectSignIn, jsonOK, signIn, submitSignIn, visitSignedOut, type Staff } from './support';
import { origin } from './target';

test('anonymous reservation deep link and one rejected sign-in never open the workspace', async ({ page }) => {
  await visitSignedOut(page, '/reservations');
  await expect(page).toHaveURL(`${origin}/login`);
  await expect(page.getByRole('heading', { name: 'Reservations', level: 1 })).toHaveCount(0);
  await expectListDenied(page, 'reservations');

  // A single synthetic unregistered identity, not a bad password for a staff member.
  const rejection = await submitSignIn(page, `e2e-absent-${randomUUID()}`, randomUUID());
  expect([400, 401], 'Expected a credential rejection (not CSRF, throttling, or server failure)').toContain(rejection.status());
  expect(rejection.headers()['content-type']).toMatch(/application\/json/i);
  expect((await rejection.json()).detail).toMatch(/invalid (username or password|credentials)/i);
  await expect(page.getByRole('alert')).toContainText(/check your username and password/i);
  await expectSignIn(page);
  await visitSignedOut(page, '/reservations');
  await expectListDenied(page, 'reservations');
});

type BriefingStay = { id: number; arrival: string; status: string };
type Dashboard = { date: string; metrics: Record<string, number | string>; reservations: BriefingStay[] };

async function expectBoard(board: Locator, stays: BriefingStay[], emptyMessage: string) {
  const table = board.getByRole('table');
  if (stays.length === 0) {
    await expect(board.getByText(emptyMessage, { exact: true })).toBeVisible();
    await expect(table).toHaveCount(0);
    return;
  }
  await expect(table.getByRole('row')).toHaveCount(1 + stays.length);
  for (const stay of stays) {
    await expect(table.getByText(`Reservation #${stay.id}`, { exact: true })).toBeVisible();
  }
}

test('staff identity survives reload and the dashboard shows live counts and the correct arrivals', async ({ page }) => {
  const staff = await signIn(page);
  const snapshot = page.getByRole('region', { name: 'Shift snapshot' });
  await expect(snapshot).toBeVisible(); // Initial load finished before we observe the new document's requests.
  const [me, reply] = await Promise.all([apiReply(page, 'auth/me'), apiReply(page, 'dashboard'), page.reload()]);
  const persisted = (await jsonOK<{ user: Staff | null }>(me)).user;
  expect(persisted?.id === staff.id && persisted?.username === staff.username, 'Reload must restore the signed-in staff session').toBe(true);
  const account = page.getByRole('complementary').filter({ has: page.getByRole('navigation', { name: 'Main navigation' }) }).locator('footer');
  await expect(account).toBeVisible();
  // Assert booleans so an ordinary missing-label diagnostic does not print the login name.
  await expect.poll(() => account.getByText(staff.full_name.trim() || staff.username, { exact: true }).isVisible(),
    { message: 'Account footer must show the signed-in identity' }).toBe(true);
  await expect.poll(() => account.getByText(staff.roles.join(' · ') || 'Staff account', { exact: true }).isVisible(),
    { message: 'Account footer must show this account’s roles' }).toBe(true);
  const main = page.getByRole('main');
  await expect(main.getByRole('heading', { level: 1, name: 'Operations overview' })).toBeVisible();

  const dashboard = await jsonOK<Dashboard>(reply);
  expect(dashboard.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  const briefingDate = main.locator('header time');
  await expect(briefingDate).toHaveAttribute('datetime', dashboard.date);
  await expect(briefingDate).toBeVisible();
  for (const [key, label] of Object.entries({
    check_ins: 'Check-ins', check_outs: 'Check-outs', available_rooms: 'Available rooms', occupied_rooms: 'Occupied rooms',
  })) {
    const value = dashboard.metrics[key];
    expect(typeof value === 'number' && Number.isInteger(value) && value >= 0, `Expected live ${key} count`).toBe(true);
    const tile = snapshot.getByRole('link').filter({ has: page.getByText(label, { exact: true }) });
    await expect(tile.getByText(Number(value).toLocaleString('en-GB'), { exact: true })).toBeVisible();
    if (key === 'check_ins' || key === 'check_outs') {
      // These API counts use scheduled arrival/departure, not timestamps of recorded actions.
      await expect(tile.getByText(/scheduled today/i)).toBeVisible();
    }
  }

  // Cross-check one total against its *source* catalog as well as the dashboard
  // response. Read only its count and never attach the body or guest identifiers.
  const guests = await page.request.get('/api/v1/guests/?page_size=1', { maxRedirects: 0 });
  try {
    expect(guests.status()).toBe(200);
    const count = (await guests.json()).count;
    expect(typeof count === 'number' && Number.isInteger(count) && count >= 0).toBe(true);
    expect(dashboard.metrics.total_guests, 'Dashboard guest total must agree with the scoped guest directory').toBe(count);
    const register = main.getByRole('region', { name: 'Property register' });
    const guestMetric = register.getByRole('link').filter({ has: page.getByText('Guest profiles', { exact: true }) });
    await expect(guestMetric.getByText(count.toLocaleString('en-GB'), { exact: true })).toBeVisible();
  } finally { await guests.dispose(); }

  expect(Array.isArray(dashboard.reservations), 'Expected the authorized reservation briefing').toBe(true);
  const board = main.getByRole('region', { name: 'Reservation board' });
  await expectBoard(board, dashboard.reservations, 'No reservations in this briefing');
  const arriving = board.getByRole('button', { name: 'Arriving today' });
  await arriving.click();
  await expect(arriving).toHaveAttribute('aria-pressed', 'true');
  await expectBoard(board, dashboard.reservations.filter(row => row.arrival === dashboard.date && row.status !== 'cancelled'), 'No matching stays');
});
