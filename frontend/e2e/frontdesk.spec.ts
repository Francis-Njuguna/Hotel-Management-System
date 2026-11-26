import { randomUUID } from 'node:crypto';
import { expect, test, type Locator, type Page } from '@playwright/test';
import { apiReply, firstPage, matchesApi, navLink, signIn, type Listing } from './support';
import { origin } from './target';

type Guest = { reference: string; full_name: string };
type Room = { number: string; category: string; capacity: number; occupied: boolean; cleanliness: string };
type Reservation = { id: number; guest_name: string; arrival: string; departure: string; status: string };
type Catalog = 'Guests' | 'Rooms' | 'Reservations';

async function navigate<T>(page: Page, label: Catalog) {
  const stem = label.toLowerCase();
  const link = navLink(page, label);
  const [reply] = await Promise.all([apiReply(page, stem, 'GET', ''), link.click()]);
  await expect(page).toHaveURL(`${origin}/${stem}`);
  await expect(link).toHaveAttribute('aria-current', 'page');
  await expect(page.getByRole('main').getByRole('heading', { level: 1, name: label, exact: true })).toBeVisible();
  return firstPage<T>(reply);
}

async function expectPageCount(region: Locator, label: Catalog, count: number) {
  const pager = region.getByRole('navigation', { name: `${label} pages` });
  const noun = label.slice(0, -1).toLowerCase();
  await expect(pager.getByText(new RegExp(`^${count}\\s+${noun}s?\\b.*\\bPage 1 of \\d+$`, 'i'))).toBeVisible();
}

async function expectGuestDirectory(page: Page, data: Listing<Guest>, filtered = false) {
  const directory = page.getByRole('region', { name: 'Guest directory' });
  const table = directory.getByRole('table', { name: 'Registered guests' });
  const empty = directory.getByText(filtered ? /no guests match this search/i : /no guest profiles yet/i);
  await expectPageCount(directory, 'Guests', data.count);
  await expect(directory.getByRole('alert')).toHaveCount(0);
  if (!data.count) {
    await expect(empty).toBeVisible();
    await expect(table).toHaveCount(0);
    return;
  }
  await expect(empty).toHaveCount(0);
  await expect(table.getByRole('row')).toHaveCount(1 + data.results.length); // Plus header row.
  const sample = data.results[0];
  const row = table.getByRole('row').filter({ has: page.getByText(sample.reference, { exact: true }) });
  await expect(row.getByText(sample.full_name, { exact: true })).toBeVisible();
}

async function expectRooms(page: Page, data: Listing<Room>) {
  const results = page.getByRole('region', { name: 'Room results' });
  await expectPageCount(results, 'Rooms', data.count);
  await expect(results.getByRole('article')).toHaveCount(data.results.length);
  await expect(results.getByRole('alert')).toHaveCount(0);
  if (!data.count) {
    await expect(results.getByText(/no rooms match/i)).toBeVisible();
    return;
  }
  const sample = data.results[0];
  await expect(results.getByText(/no rooms match/i)).toHaveCount(0);
  const card = results.getByRole('article', { name: `Room ${sample.number}`, exact: true });
  await expect(card.getByText(`${sample.category} · Sleeps ${sample.capacity}`, { exact: true })).toBeVisible();
  const condition = card.getByRole('list', { name: 'Current room condition' });
  expect(typeof sample.occupied).toBe('boolean');
  expect(['dirty', 'inspected']).toContain(sample.cleanliness);
  await expect(condition.getByText(sample.occupied ? 'Occupied now' : 'Unoccupied now', { exact: true })).toBeVisible();
  await expect(condition.getByText(sample.cleanliness === 'inspected' ? 'Inspected' : 'Needs cleaning', { exact: true })).toBeVisible();
}

test('front desk opens each authorized catalog and reconciles its data or explicit empty state', async ({ page }) => {
  await signIn(page);
  const guests = await navigate<Guest>(page, 'Guests');
  await expectGuestDirectory(page, guests);
  const rooms = await navigate<Room>(page, 'Rooms');
  await expectRooms(page, rooms);
  const bookings = await navigate<Reservation>(page, 'Reservations');
  const directory = page.getByRole('region', { name: 'Reservation directory' });
  const table = directory.getByRole('table', { name: 'Reservations and stay actions' });
  await expectPageCount(directory, 'Reservations', bookings.count);
  await expect(directory.getByRole('alert')).toHaveCount(0);
  if (bookings.count) {
    await expect(directory.getByText(/no reservations have been recorded/i)).toHaveCount(0);
    await expect(table.getByRole('row')).toHaveCount(bookings.results.length + 1);
    const sample = bookings.results[0];
    const row = table.getByRole('row').filter({ has: page.getByText(`Reservation #${sample.id}`, { exact: true }) });
    await expect(row.getByText(sample.guest_name, { exact: true })).toBeVisible();
    await expect(row.locator('time').nth(0)).toHaveAttribute('datetime', sample.arrival);
    await expect(row.locator('time').nth(1)).toHaveAttribute('datetime', sample.departure);
    const state = sample.status.replaceAll('_', ' ').replace(/^./, letter => letter.toUpperCase());
    await expect(row.getByText(state, { exact: true })).toBeVisible();
  } else {
    await expect(directory.getByText(/no reservations have been recorded/i)).toBeVisible();
    await expect(table).toHaveCount(0);
  }
});

test('a failed guest search is not an empty result; retry gets a live zero count and Clear restores the directory', async ({ page }) => {
  await signIn(page);
  const before = await navigate<Guest>(page, 'Guests');
  expect(before.count, 'Fixture requires a synthetic guest (e.g. seed_demo) to distinguish stale data, failure, no matches and restored data').toBeGreaterThan(0);
  await expectGuestDirectory(page, before);
  const directory = page.getByRole('region', { name: 'Guest directory' });
  const search = directory.getByRole('searchbox', { name: 'Search guests' });
  const marker = `hms-e2e-no-match-${randomUUID()}`;
  await search.fill(marker);

  // One browser-local transport failure, NOT a fabricated API response. Keep
  // the Vite HMR connection, Django session and unrelated requests online.
  await page.route(url => url.origin === origin && url.pathname === '/api/v1/guests/' && url.searchParams.get('search') === marker,
    route => route.abort('connectionfailed'), { times: 1 });
  await Promise.all([
    page.waitForEvent('requestfailed', { predicate: req => matchesApi(req, 'guests', 'GET', marker), timeout: 10_000 }),
    search.press('Enter'),
  ]);
  await expect(directory.getByRole('alert')).toContainText(/failed|network|connection|unavailable/i);
  await expect(directory.getByText(/no guest profiles|no guests match/i)).toHaveCount(0);
  await expect(directory.getByRole('table')).toHaveCount(0); // No stale results for a different query.

  const [retried] = await Promise.all([
    apiReply(page, 'guests', 'GET', marker), directory.getByRole('button', { name: 'Retry', exact: true }).click(),
  ]);
  const noMatches = await firstPage<Guest>(retried);
  expect(noMatches.count, 'The unique search marker must have no real matches').toBe(0);
  await expectGuestDirectory(page, noMatches, true);
  const [cleared] = await Promise.all([
    apiReply(page, 'guests', 'GET', ''), directory.getByRole('button', { name: 'Clear', exact: true }).click(),
  ]);
  const restored = await firstPage<Guest>(cleared);
  expect(restored.count, 'Clearing the filter restores the original fixture count').toBe(before.count);
  const references = new Set(restored.results.map(guest => guest.reference));
  expect(references.size === before.results.length && before.results.every(guest => references.has(guest.reference)),
    'The cleared first page must contain the original fixture identities').toBe(true);
  await expect(search).toHaveValue('');
  await expectGuestDirectory(page, restored);
});
