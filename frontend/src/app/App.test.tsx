import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, type SessionUser } from '../services/api';
import { SessionProvider } from '../services/session';
import { App } from './App';
import { resumePath } from './navigation';

vi.mock('../services/api', async (original) => ({ ...await original<typeof import('../services/api')>(), api: vi.fn() }));
const get = vi.mocked(api);
const fixture: SessionUser = { id: 9, username: 'fixture-repairs', full_name: 'Fixture Technician', roles: ['Maintenance Staff'], capabilities: ['dashboard.view', 'maintenance.view', 'maintenance.work'] };
function visit(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><SessionProvider><App /></SessionProvider></MemoryRouter>);
}

describe('workspace boundary', () => {
  beforeEach(() => { get.mockReset(); });
  it('does not mount or request an unauthorized catalog at its direct URL', async () => {
    get.mockResolvedValueOnce({ user: fixture });
    visit('/guests');
    expect(await screen.findByRole('heading', { name: /isn’t available to you/i })).toBeInTheDocument();
    const rail = within(screen.getByRole('navigation', { name: 'Main navigation' }));
    expect(rail.getByRole('link', { name: 'Maintenance' })).toHaveAttribute('href', '/housekeeping');
    expect(rail.queryByRole('link', { name: /guests|billing|housekeeping/i })).not.toBeInTheDocument();
    expect(get.mock.calls.map(([path]) => path)).toEqual(['auth/me/']);
  });
  it('distinguishes a failed session check from a verified signed-out session', async () => {
    get.mockRejectedValueOnce(new Error('fixture transport failure')).mockResolvedValueOnce({ user: null });
    visit('/reservations');
    expect(await screen.findByRole('alert')).toHaveTextContent('session service is unavailable');
    expect(screen.queryByRole('button', { name: 'Sign in' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByRole('heading', { name: 'Staff sign in' })).toBeInTheDocument();
    expect(get.mock.calls.map(([path]) => path)).toEqual(['auth/me/', 'auth/me/']);
  });
  it('only resumes known workspace addresses on the current origin', () => {
    expect(resumePath('/reservations?reservation=12')).toBe('/reservations?reservation=12');
    expect(resumePath('/verify-email/fixture:id_signature')).toBe('/verify-email/fixture:id_signature');
    for (const unsafe of ['//elsewhere.invalid/', '/\\elsewhere.invalid/', '/api/v1/staff/', '/login', '/verify-email/fixture/extra', '/verify-email/%2Fother', null, { pathname: '/' }]) {
      expect(resumePath(unsafe)).toBe('/');
    }
  });
});
