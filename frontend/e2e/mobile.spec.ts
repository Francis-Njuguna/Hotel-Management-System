import { expect, test } from '@playwright/test';
import { apiReply, expectListDenied, expectSignIn, firstPage, navLink, signIn, visitSignedOut } from './support';
import { origin } from './target';

test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });

test('mobile drawer navigates and signs out; Back and a fresh protected visit stay signed out', async ({ page }) => {
  await signIn(page);
  const open = page.getByRole('button', { name: 'Open navigation' });
  const drawer = page.getByRole('dialog', { name: 'Workspace menu' });
  await expect(open).toHaveAttribute('aria-expanded', 'false');
  await expect(navLink(page, 'Rooms')).toBeHidden();
  await open.tap();
  await expect(drawer).toBeVisible();
  await expect(drawer.getByRole('button', { name: 'Close navigation' })).toBeVisible();
  const [response] = await Promise.all([apiReply(page, 'rooms'), navLink(page, 'Rooms').tap()]);
  const rooms = await firstPage<{ number: string }>(response);
  await expect(page).toHaveURL(`${origin}/rooms`);
  await expect(page.getByRole('heading', { level: 1, name: 'Rooms' })).toBeVisible();
  await expect(drawer).toBeHidden();
  await expect(open).toHaveAttribute('aria-expanded', 'false');
  const results = page.getByRole('region', { name: 'Room results' });
  if (rooms.count) {
    await expect(results.getByRole('heading', { name: `Room ${rooms.results[0].number}`, exact: true })).toBeVisible();
  } else {
    await expect(results.getByText(/no rooms match/i)).toBeVisible();
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1),
    'Room catalog must not force page-wide horizontal scrolling on a phone').toBe(true);

  await open.tap();
  const [logout] = await Promise.all([
    apiReply(page, 'auth/logout', 'POST'), drawer.getByRole('button', { name: 'Sign out', exact: true }).tap(),
  ]);
  expect(logout.ok(), 'Server must accept the UI sign-out').toBe(true);
  await expectSignIn(page);
  await expect(results).toHaveCount(0);
  await expectListDenied(page, 'rooms'); // Same resource that just succeeded; the cookie jar is now denied.
  await page.goBack(); // The overview was visited in this same browser context.
  await expectSignIn(page);
  await expect(page.getByRole('region', { name: 'Shift snapshot' })).toHaveCount(0);
  await visitSignedOut(page, '/rooms'); // Also re-boot the SPA; GET me must return user:null.
  await expect(page.getByRole('region', { name: 'Room results' })).toHaveCount(0);
});
