import { fireEvent, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { StaffPage } from '../index';
import type { AuditEvent, StaffMember } from '../model';
import { mountOffice, paged } from './transport';

const member: StaffMember = {
  id: 14, username: 'test-staff', first_name: 'Test', last_name: 'Staff', email: 'staff@example.invalid',
  department: 'Front desk', role: 'Receptionist', is_active: true,
};
const admin = ['staff.manage', 'audit.view'];
const button = (name: string) => screen.getByRole('button', { name });
const fill = (name: string, value: string) => fireEvent.change(screen.getByLabelText(name, { exact: true }), { target: { value } });

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('StaffPage', () => {
  it('uses the paginated audit feed and never requests staff accounts on audit-only access', async () => {
    const event: AuditEvent = { id: 4, actor: 8, actor_name: 'fixture-operator', verb: 'staff.updated',
      entity: 'auth.user', object_id: 14, summary: 'Staff account updated', created_at: '2026-03-01T10:11:00Z' };
    const calls = mountOffice(<StaffPage />, ['audit.view'], ({ path }) => {
      if (path === 'audit/?page=1') return paged([event], { count: 26, next: '?page=2' });
      if (path === 'audit/?page=2') return paged([{ ...event, id: 2, actor: null, actor_name: null, verb: 'staff.created',
        summary: 'Staff account created' }], { count: 26, previous: '?page=1' });
      throw new Error(`Unexpected path ${path}`);
    });
    const activity = await screen.findByRole('table', { name: 'Recorded activity' });
    expect(activity).toHaveTextContent('fixture-operator (#8)');
    expect(activity).toHaveTextContent('auth.user #14'); expect(activity).toHaveTextContent('staff.updated');
    expect(within(activity).getByText('Staff account updated')).toBeVisible();
    fireEvent.click(button('Next'));
    expect(await screen.findByText('No staff actor')).toBeVisible();
    expect(screen.getByText('staff.created')).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Register staff' })).not.toBeInTheDocument();
    expect(calls.map(c => c.path)).toEqual(['auth/me/', 'audit/?page=1', 'audit/?page=2']);
  });

  it('requests neither sensitive list without a staff or audit grant', async () => {
    const calls = mountOffice(<StaffPage />, ['billing.view'], () => { throw new Error('Unpermitted read'); });
    expect(await screen.findByText(/do not have access to staff accounts/i)).toBeVisible();
    expect(calls.map(c => c.path)).toEqual(['auth/me/']);
  });

  it('registers only after password confirmation and a role review that does not expose the password', async () => {
    const secret = ' Synthetic-test-only passphrase! ';
    let created = false;
    const calls = mountOffice(<StaffPage />, admin, ({ path, method }) => {
      if (path === 'staff/?page=1') return paged(created ? [member] : []);
      if (path === 'staff/' && method === 'POST') { created = true; return member; }
      throw new Error(`Unexpected path ${path}`);
    });
    fireEvent.click(await screen.findByRole('button', { name: 'Register staff' }));
    expect(screen.getByLabelText('Role', { exact: true })).toHaveValue('');
    fill('Username', member.username); fill('First name', member.first_name); fill('Last name', member.last_name);
    fill('Email', member.email); fill('Department', member.department); fill('Role', member.role);
    expect(screen.getByLabelText('New password', { exact: true })).toHaveAttribute('type', 'password');
    fill('New password', secret); fill('Confirm new password', 'different test input'); fireEvent.click(button('Review account'));
    expect(screen.getByRole('alert')).toHaveTextContent(/matching new passwords/);
    fill('Confirm new password', secret); fireEvent.click(button('Review account'));
    const review = screen.getByRole('form', { name: 'Review account' });
    expect(review).toHaveTextContent('Receptionist'); expect(review).not.toHaveTextContent(secret.trim());
    expect(review.querySelector('input[type="password"]')).toBeNull();
    expect(calls.filter(c => c.method === 'POST')).toHaveLength(0);
    fireEvent.click(button('Create account'));
    expect(await screen.findByText('Account created for test-staff.')).toBeVisible();
    expect(calls.filter(c => c.method === 'POST')).toEqual([{ method: 'POST', path: 'staff/', body: {
      username: member.username, first_name: member.first_name, last_name: member.last_name, email: member.email,
      department: member.department, role: member.role, is_active: true, password: secret,
    } }]);
  });

  it('uses server pagination/search, then PATCHes only the changed role and department', async () => {
    const other = { ...member, id: 16, username: 'other-fixture', first_name: 'Other', department: 'Kitchen' };
    let current = member;
    const calls = mountOffice(<StaffPage />, ['staff.manage'], ({ path, method }) => {
      if (path === 'staff/?page=1') return paged([other], { count: 26, next: '?page=2' });
      if (path === 'staff/?page=2') return paged([current], { count: 26, previous: '?page=1' });
      if (path === 'staff/?page=1&search=test-staff') return paged([current]);
      if (path === 'staff/14/' && method === 'PATCH') { current = { ...member, department: 'Test finance', role: 'Accountant' }; return current; }
      throw new Error(`Unexpected path ${path}`);
    });
    await screen.findByRole('button', { name: 'Edit other-fixture' }); fireEvent.click(button('Next'));
    await screen.findByRole('button', { name: 'Edit test-staff' });
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search directory' }), { target: { value: 'test-staff' } }); fireEvent.click(button('Search'));
    expect(await screen.findByText('Page 1 · 1 account')).toBeVisible();
    fireEvent.click(button('Edit test-staff'));
    expect(screen.queryByLabelText('New password', { exact: true })).not.toBeInTheDocument();
    fill('Role', 'Accountant'); fill('Department', 'Test finance'); fireEvent.click(button('Review changes'));
    expect(screen.getByText('Receptionist → Accountant')).toBeVisible();
    expect(calls.filter(c => c.method === 'PATCH')).toHaveLength(0);
    fireEvent.click(button('Confirm changes'));
    expect(await screen.findByRole('table', { name: 'Staff accounts' })).toHaveTextContent('Accountant');
    expect(calls.filter(c => c.method === 'PATCH')).toEqual([{ method: 'PATCH', path: 'staff/14/', body: { role: 'Accountant', department: 'Test finance' } }]);
    expect(calls.some(c => c.path.startsWith('audit/'))).toBe(false);
  });

  it('does not allow self-deactivation or self-role edits; password replacement is explicit and refreshes the session', async () => {
    const self = { ...member, id: 8, username: 'fixture-operator', role: 'Super Administrator' };
    const calls = mountOffice(<StaffPage />, admin, ({ path }) => {
      if (path === 'staff/?page=1') return paged([self]);
      if (path === 'staff/8/') return self;
      throw new Error(`Unexpected path ${path}`);
    });
    await screen.findByRole('button', { name: 'Edit fixture-operator' });
    expect(screen.queryByRole('button', { name: /Deactivate/ })).not.toBeInTheDocument();
    fireEvent.click(button('Edit fixture-operator')); expect(screen.getByLabelText('Role', { exact: true })).toBeDisabled();
    const toggle = screen.getByRole('checkbox', { name: 'Set a new password' }); fireEvent.click(toggle);
    fill('New password', 'discard this test input'); fireEvent.click(toggle); fireEvent.click(toggle);
    expect(screen.getByLabelText('New password', { exact: true })).toHaveValue('');
    const synthetic = 'Replacement for component test only';
    fill('New password', synthetic); fill('Confirm new password', synthetic); fireEvent.click(button('Review changes'));
    expect(screen.getByRole('form', { name: 'Review account' })).not.toHaveTextContent(synthetic);
    fireEvent.click(button('Confirm changes'));
    expect(await screen.findByText('Changes saved for fixture-operator.')).toBeVisible();
    expect(calls.filter(c => c.method === 'PATCH')).toEqual([{ method: 'PATCH', path: 'staff/8/', body: { password: synthetic } }]);
    expect(calls.filter(c => c.path === 'auth/me/')).toHaveLength(2);
  });

  it('allows a safe cancel and requires a separate confirmation for each status transition', async () => {
    let current = member;
    const calls = mountOffice(<StaffPage />, admin, ({ path, method, body }) => {
      if (path === 'staff/?page=1') return paged([current]);
      if (path === 'staff/14/' && method === 'PATCH') {
        current = { ...member, is_active: (body as { is_active: boolean }).is_active }; return current;
      }
      throw new Error(`Unexpected path ${path}`);
    });
    fireEvent.click(await screen.findByRole('button', { name: 'Deactivate test-staff' }));
    expect(screen.getByRole('form', { name: 'Confirm account status change' })).toHaveTextContent('test-staff');
    fireEvent.click(button('Cancel'));
    fireEvent.click(await screen.findByRole('button', { name: 'Deactivate test-staff' }));
    expect(calls.filter(c => c.method !== 'GET')).toHaveLength(0);
    fireEvent.click(button('Confirm deactivation'));
    fireEvent.click(await screen.findByRole('button', { name: 'Activate test-staff' }));
    fireEvent.click(button('Confirm activation'));
    expect(await screen.findByText('test-staff is now active.')).toBeVisible();
    expect(calls.filter(c => c.method !== 'GET')).toEqual([
      { method: 'PATCH', path: 'staff/14/', body: { is_active: false } },
      { method: 'PATCH', path: 'staff/14/', body: { is_active: true } },
    ]);
  });
});
