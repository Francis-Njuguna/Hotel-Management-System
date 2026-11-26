import { randomBytes } from 'node:crypto';
import { expect, test, type Locator, type Page } from '@playwright/test';
import { apiReply, expectSignIn, jsonOK, signIn, submitSignIn, visitSignedOut, type Staff } from './support';
import { origin } from './target';

test.skip(process.env.HMS_E2E_DISPOSABLE !== '1' || process.env.HMS_E2E_ADMIN !== '1', 'Disposable admin rehearsal only.');
const button = (scope: Page | Locator, name: string) => scope.getByRole('button', { name, exact: true });
const link = (page: Page, name: string) => page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name, exact: true });

// Generate different-sized fixture photos in memory. No operator file or external asset is used.
async function photo(page: Page, width: number) {
  const data = await page.evaluate(w => {
    const canvas = document.createElement('canvas'); canvas.width = w; canvas.height = 6;
    const ctx = canvas.getContext('2d')!; ctx.fillStyle = 'navy'; ctx.fillRect(0, 0, w, 6);
    return canvas.toDataURL('image/png').split(',')[1];
  }, width);
  return { name: 'fixture.png', mimeType: 'image/png', buffer: Buffer.from(data, 'base64') };
}

async function savePhoto(page: Page, save: Locator, endpoint: string, folder: string) {
  const [response] = await Promise.all([apiReply(page, endpoint, 'POST'), save.click()]);
  expect(response.status()).toBe(201);
  const { image } = await response.json();
  expect(typeof image === 'string' && image.startsWith(`/api/v1/media/${folder}/`)).toBe(true);
  return new URL(image, origin).href;
}

async function displayed(image: Locator, url: string, width: number) {
  await image.scrollIntoViewIfNeeded(); // catalog thumbnails are lazy-loaded
  await expect.poll(() => image.evaluate((el, expected) => el instanceof HTMLImageElement && el.src === expected.url &&
    el.complete && el.naturalWidth === expected.width && el.naturalHeight === 6, { url, width })).toBe(true);
}

test('administrator creates a room and menu item with photos that display after reload', async ({ page }) => {
  test.setTimeout(120_000);
  const admin = await signIn(page);
  expect(admin.roles).toEqual(['Super Administrator']);
  const tag = randomBytes(5).toString('hex'), number = `IMG-${tag}`, dish = `Synthetic plate ${tag}`;
  await link(page, 'Rooms').click();
  await button(page, 'Add room').click();
  const room = page.getByRole('dialog', { name: 'Add room' });
  await room.getByLabel('Room number (required)').fill(number);
  await room.getByLabel('Nightly rate (KES)').fill('3600.00');
  await room.getByLabel('Room photo', { exact: true }).setInputFiles(await photo(page, 8));
  const roomURL = await savePhoto(page, button(room, 'Create room'), 'rooms', 'rooms');
  await page.reload();
  await displayed(page.getByRole('img', { name: `Room ${number}`, exact: true }), roomURL, 8);

  await link(page, 'Restaurant').click();
  await button(page, 'Menu items').click();
  await button(page, 'New menu item').click();
  const menu = page.getByRole('form', { name: 'New menu item' });
  await menu.getByLabel('Item name').fill(dish);
  await menu.getByLabel('Category').fill('Lunch');
  await menu.getByLabel('Unit price (KES)').fill('125.50');
  await menu.getByLabel('Item image (optional)').setInputFiles(await photo(page, 11));
  const menuURL = await savePhoto(page, button(menu, 'Create menu item'), 'menu-items', 'menu');
  await page.reload();
  await button(page, 'Menu items').click();
  await displayed(page.getByRole('article', { name: dish }).locator('img'), menuURL, 11);
});

test('administrator creates a receptionist, then changes the role and the staff access', async ({ page, browser }) => {
  test.setTimeout(120_000);
  const admin = await signIn(page);
  expect(admin.capabilities).toContain('staff.manage');
  const username = `qa-desk-${randomBytes(5).toString('hex')}`, password = randomBytes(24).toString('base64url');
  await link(page, 'Staff & activity').click();
  await button(page, 'Register staff').click();
  const entry = page.getByRole('form', { name: 'Register staff account' });
  await entry.getByLabel('Username').fill(username);
  await entry.getByLabel('Email').fill(`${username}@example.invalid`);
  await entry.getByLabel('Role').selectOption('Receptionist');
  try {
    await entry.getByLabel('New password', { exact: true }).fill(password);
    await entry.getByLabel('Confirm new password', { exact: true }).fill(password);
  } catch { throw new Error('Could not fill the initial password fields. Values withheld.'); }
  await button(entry, 'Review account').click();
  const review = page.getByRole('form', { name: 'Review account' });
  await expect(review).toContainText('Receptionist');
  const [created] = await Promise.all([apiReply(page, 'staff', 'POST'), button(review, 'Create account').click()]);
  expect(created.status()).toBe(201);
  const member = await created.json();
  expect(member).toMatchObject({ username, role: 'Receptionist', is_active: true });
  await expect(page.getByRole('row').filter({ hasText: username })).toContainText('Receptionist');

  const session = await browser.newContext({ baseURL: origin });
  try {
    const staff = await session.newPage();
    await visitSignedOut(staff, '/');
    const login = async () => (await jsonOK<{ user: Staff }>(await submitSignIn(staff, username, password))).user;
    expect(await login()).toMatchObject({ id: member.id, roles: ['Receptionist'] });
    await link(staff, 'Reservations').click();
    await expect(button(staff, 'New reservation')).toBeVisible();
    const denied = await staff.request.get('/api/v1/staff/', { maxRedirects: 0 });
    try { expect(denied.status()).toBe(403); } finally { await denied.dispose(); }

    await button(page, `Edit ${username}`).click();
    const edit = page.getByRole('form', { name: 'Edit staff account' });
    await edit.getByLabel('Role').selectOption('Restaurant Staff');
    await button(edit, 'Review changes').click();
    const [changed] = await Promise.all([apiReply(page, `staff/${member.id}`, 'PATCH'), button(review, 'Confirm changes').click()]);
    expect(changed.status()).toBe(200);
    await expect(page.getByRole('row').filter({ hasText: username })).toContainText('Restaurant Staff');
    await staff.reload();
    await expectSignIn(staff);
    // Use the ordinary sign-in page rather than resuming a reservation deep link after the role change.
    await staff.goto('/login');
    expect(await login()).toMatchObject({ id: member.id, roles: ['Restaurant Staff'] });
    await link(staff, 'Restaurant').click();
    await expect(button(staff, 'Menu items')).toBeVisible();
    const restricted = await staff.request.get('/api/v1/reservations/', { maxRedirects: 0 });
    try { expect(restricted.status()).toBe(403); } finally { await restricted.dispose(); }
  } finally { await session.close(); }
});
