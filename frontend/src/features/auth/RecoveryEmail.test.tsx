import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../app/App';
import { api, ApiError, send, type SessionUser } from '../../services/api';
import { SessionProvider } from '../../services/session';

vi.mock('../../services/api', async (original) => ({ ...await original<typeof import('../../services/api')>(), api: vi.fn(), send: vi.fn() }));
const get = vi.mocked(api);
const post = vi.mocked(send);
const first: SessionUser = { id: 4, username: 'fixture-wrong', full_name: 'First Fixture', roles: [], capabilities: [] };
const second: SessionUser = { ...first, id: 5, username: 'fixture-requester', full_name: 'Second Fixture' };
// This probe renders only the boolean result, never the raw link.
function CleanAddressProbe() { return useLocation().pathname === '/verify-email' ? <span>Address has no token</span> : null; }
function visit(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><SessionProvider><App /><CleanAddressProbe /></SessionProvider></MemoryRouter>);
}
async function signIn(username: string) {
  fireEvent.change(await screen.findByLabelText('Username', { exact: true }), { target: { value: username } });
  fireEvent.change(screen.getByLabelText('Password', { exact: true }), { target: { value: 'fixture-only value' } });
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
}

describe('signed-in recovery address verification', () => {
  beforeEach(() => { get.mockReset(); post.mockReset(); });
  it('requests verification for the current staff account without taking a typed address or exposing API detail', async () => {
    get.mockResolvedValue({ user: first }); post.mockResolvedValueOnce({ detail: 'Private fixture state.' });
    visit('/verify-email');
    const account = within(await screen.findByRole('complementary'));
    await userEvent.click(account.getByRole('button', { name: 'Send verification email' }));
    expect(await account.findByText(/if your account has an eligible recovery address/i)).toBeVisible();
    expect(post).toHaveBeenCalledExactlyOnceWith('auth/recovery-email/', 'POST', {});
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByText('Private fixture state.')).not.toBeInTheDocument();
  });
  it('requires explicit confirmation, rejects a wrong account, resumes the link after account switching, and removes it on success', async () => {
    const opaque = 'fixture:opaque_link';
    get.mockResolvedValueOnce({ user: null }).mockResolvedValueOnce({ user: first })
      .mockResolvedValueOnce({ user: null }).mockResolvedValueOnce({ user: second });
    post.mockResolvedValueOnce({ user: first }).mockRejectedValueOnce(new ApiError(403, {}, 'Fixture detail not for display.'))
      .mockResolvedValueOnce(null).mockResolvedValueOnce({ user: second }).mockResolvedValueOnce({ detail: 'Confirmed.' });
    visit(`/verify-email/${opaque}`);
    await signIn(first.username);
    const confirm = await screen.findByRole('button', { name: 'Confirm recovery email' });
    expect(post.mock.calls.map(([path]) => path)).toEqual(['auth/login/']);
    expect(within(screen.getByRole('main')).getByText(first.username)).toBeVisible();
    await userEvent.click(confirm);
    expect(await screen.findByRole('alert')).toHaveTextContent('could not be confirmed for this staff account');
    expect(screen.queryByText('Recovery email verified')).not.toBeInTheDocument();
    expect(screen.queryByText('Fixture detail not for display.')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    await signIn(second.username);
    const retry = await screen.findByRole('button', { name: 'Confirm recovery email' });
    expect(within(screen.getByRole('main')).getByText(second.username)).toBeVisible();
    await userEvent.click(retry);
    expect(await screen.findByText('Recovery email verified')).toBeVisible();
    expect(screen.getByText('Address has no token')).toBeInTheDocument();
    expect(document.title).not.toContain(opaque); expect(document.body).not.toHaveTextContent(opaque);
    expect(post.mock.calls.filter(([path]) => path === 'auth/recovery-email/confirm/')).toEqual([
      ['auth/recovery-email/confirm/', 'POST', { token: opaque }], ['auth/recovery-email/confirm/', 'POST', { token: opaque }],
    ]);
  });
});
