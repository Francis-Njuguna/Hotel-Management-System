import { expect, type Page, type Request, type Response } from '@playwright/test';
import { origin } from './target';

export type Staff = { id: number; username: string; full_name: string; roles: string[]; capabilities: string[] };
type Session = { user: Staff | null };
export type Listing<T> = { count: number; previous: string | null; next: string | null; results: T[] };

export function matchesApi(req: Request, endpoint: string, method: string, search?: string) {
  const url = new URL(req.url());
  return req.method() === method && url.origin === origin && url.pathname === `/api/v1/${endpoint}/` &&
    (search === undefined || (url.searchParams.get('search') ?? '') === search);
}

// Arm before the UI action. Wait for the completed body rather than observing
// an abandoned read from React StrictMode or issuing a second oracle request.
export async function apiReply(page: Page, endpoint: string, method = 'GET', search?: string): Promise<Response> {
  const req = await page.waitForEvent('requestfinished', {
    predicate: r => matchesApi(r, endpoint, method, search), timeout: 20_000,
  });
  const response = await req.response();
  if (!response) throw new Error(`No completed ${method} response for ${endpoint}.`);
  return response;
}

export async function jsonOK<T>(response: Response): Promise<T> {
  expect(response.status(), 'Expected a successful live API response').toBe(200);
  expect(response.headers()['content-type']).toMatch(/application\/json/i);
  return await response.json() as T;
}

export async function firstPage<T>(response: Response): Promise<Listing<T>> {
  const data = await jsonOK<Listing<T>>(response);
  expect(Array.isArray(data.results), 'DRF list must contain a results array').toBe(true);
  expect(Number.isInteger(data.count) && data.count >= data.results.length, 'Invalid DRF count').toBe(true);
  expect(data.results.length === 0, 'An empty first page must have a zero count').toBe(data.count === 0);
  expect(data.previous === null && (data.count > data.results.length ? typeof data.next === 'string' : data.next === null),
    'Expected consistent first-page links').toBe(true);
  return data;
}

export async function expectSignIn(page: Page) {
  await expect(page.getByRole('heading', { level: 1, name: /staff sign in/i })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Username', exact: true })).toBeVisible();
  await expect(page.getByLabel('Password', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Password', { exact: true })).toHaveAttribute('type', 'password');
  await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Reservations', exact: true })).toHaveCount(0);
}

export async function visitSignedOut(page: Page, path: string) {
  const [me] = await Promise.all([apiReply(page, 'auth/me'), page.goto(path)]);
  expect((await jsonOK<Session>(me)).user === null, 'Expected an anonymous session').toBe(true);
  await expectSignIn(page);
}

export async function submitSignIn(page: Page, username: string, password: string) {
  // Avoid logging form values or serializing session state into a fixture.
  expect(new URL(page.url()).origin === origin, 'Refusing to enter credentials off origin').toBe(true);
  const secret = page.getByLabel('Password', { exact: true });
  try {
    await page.getByRole('textbox', { name: 'Username', exact: true }).fill(username);
    await secret.fill(password);
  } catch {
    throw new Error('Could not fill the staff sign-in fields. Values withheld.');
  }
  const [login] = await Promise.all([apiReply(page, 'auth/login', 'POST'), secret.press('Enter')]);
  return login;
}

export async function signIn(page: Page): Promise<Staff> {
  const username = process.env.HMS_DEMO_USER?.trim();
  const password = process.env.HMS_DEMO_PASSWORD;
  if (!username || !password) throw new Error('Provide HMS_DEMO_USER and HMS_DEMO_PASSWORD for a local front-desk demo account.');
  await visitSignedOut(page, '/');
  const { user } = await jsonOK<Session>(await submitSignIn(page, username, password));
  if (!user || user.username !== username || !Number.isInteger(user.id)) throw new Error('Staff sign-in did not return the expected session identity.');
  for (const grant of ['dashboard.view', 'guests.view', 'rooms.view', 'reservations.view']) {
    expect(user.capabilities?.includes(grant), `Demo fixture requires ${grant}`).toBe(true);
  }
  await expect(page).toHaveURL(`${origin}/`);
  return user;
}

export function navLink(page: Page, name: 'Guests' | 'Rooms' | 'Reservations') {
  return page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name, exact: true });
}

// Same cookie jar as the UI; a hidden workspace is not evidence of server denial.
export async function expectListDenied(page: Page, endpoint: 'rooms' | 'reservations') {
  const denied = await page.request.get(`/api/v1/${endpoint}/`, { maxRedirects: 0 });
  try {
    expect([401, 403], `Signed-out ${endpoint} read must be denied`).toContain(denied.status());
    expect(denied.headers()['content-type']).toMatch(/application\/json/i);
    const body = await denied.json();
    expect(typeof body?.detail === 'string' && !('results' in body), 'Expected an API denial, not a list').toBe(true);
  } finally { await denied.dispose(); }
}
