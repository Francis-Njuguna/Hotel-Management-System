import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, send, type SessionUser } from '../../services/api';
import { SessionProvider } from '../../services/session';
import { ConfirmResetPage, LoginPage, RequestResetPage } from './AuthPages';

// Synthetic staff identity. Production routes import only the same-origin services.
vi.mock('../../services/api', async (original) => ({ ...await original<typeof import('../../services/api')>(), api: vi.fn(), send: vi.fn() }));
const get = vi.mocked(api);
const post = vi.mocked(send);
const staff: SessionUser = { id: 1, username: 'fixture-staff', full_name: 'Fixture Staff', roles: ['Receptionist'], capabilities: ['reservations.view'] };
function visit(path: string, from?: string) {
  return render(<MemoryRouter initialEntries={[{ pathname: path, state: { from } }]}><SessionProvider><Routes>
    <Route path="/login" element={<LoginPage />} /><Route path="/reset" element={<RequestResetPage />} />
    <Route path="/reset/:uid/:token" element={<ConfirmResetPage />} /><Route path="/reservations" element={<h1>Fixture reservation destination</h1>} />
  </Routes></SessionProvider></MemoryRouter>);
}

describe('staff authentication forms', () => {
  beforeEach(() => { get.mockReset(); post.mockReset(); });
  it('sends one sign-in, preserves password whitespace, rechecks the session and resumes the original area', async () => {
    get.mockResolvedValueOnce({ user: null }).mockResolvedValueOnce({ user: staff });
    let finish!: (value: { user: SessionUser }) => void;
    post.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    visit('/login', '/reservations');
    const username = await screen.findByLabelText('Username');
    const password = screen.getByLabelText('Password', { exact: true });
    fireEvent.change(username, { target: { value: ' fixture-staff ' } });
    fireEvent.change(password, { target: { value: ' fixture value ' } });
    const form = password.closest('form')!;
    fireEvent.submit(form); fireEvent.submit(form);
    expect(post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledWith('auth/login/', 'POST', { username: 'fixture-staff', password: ' fixture value ' });
    expect(screen.getByRole('button', { name: /signing in/i })).toBeDisabled();
    await act(async () => { finish({ user: staff }); });
    expect(await screen.findByRole('heading', { name: 'Fixture reservation destination' })).toBeInTheDocument();
    expect(get.mock.calls.map(([path]) => path)).toEqual(['auth/me/', 'auth/me/']);
  });
  it('validates email, allows retry on failure, and never exposes account existence or the raw reset response', async () => {
    get.mockResolvedValue({ user: null });
    post.mockRejectedValueOnce(new Error('fixture offline')).mockResolvedValueOnce({ detail: 'Private fixture response: account matched.' });
    visit('/reset');
    const person = userEvent.setup();
    const email = await screen.findByLabelText('Staff email');
    await person.click(screen.getByRole('button', { name: 'Request reset link' }));
    expect(email).toHaveAttribute('aria-invalid', 'true'); expect(email).toHaveFocus(); expect(post).not.toHaveBeenCalled();
    fireEvent.change(email, { target: { value: 'fixture@example.invalid' } });
    await person.click(screen.getByRole('button', { name: 'Request reset link' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not submit'); expect(email).toHaveValue('fixture@example.invalid');
    await person.click(screen.getByRole('button', { name: 'Request reset link' }));
    expect(await screen.findByRole('status')).toHaveTextContent('If an eligible account matches');
    expect(screen.queryByText(/private fixture response/i)).not.toBeInTheDocument();
    expect(post).toHaveBeenLastCalledWith('auth/reset/', 'POST', { email: 'fixture@example.invalid' });
  });
  it('rejects a mismatched confirmation before sending and posts the token only as part of the reset command', async () => {
    get.mockResolvedValue({ user: null }); post.mockResolvedValueOnce({ detail: 'Changed.' });
    visit('/reset/fixture-id/fixture-token');
    const person = userEvent.setup();
    fireEvent.change(await screen.findByLabelText('New password', { exact: true }), { target: { value: 'fixture reset value' } });
    const confirmation = screen.getByLabelText('Confirm password', { exact: true });
    fireEvent.change(confirmation, { target: { value: 'different' } });
    await person.click(screen.getByRole('button', { name: 'Save new password' }));
    expect(confirmation).toHaveFocus(); expect(post).not.toHaveBeenCalled();
    fireEvent.change(confirmation, { target: { value: 'fixture reset value' } });
    await person.click(screen.getByRole('button', { name: 'Save new password' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Password changed');
    await waitFor(() => expect(post).toHaveBeenCalledWith('auth/reset/confirm/', 'POST', { uid: 'fixture-id', token: 'fixture-token', password: 'fixture reset value' }));
    expect(screen.queryByText('fixture-token')).not.toBeInTheDocument();
  });
});
