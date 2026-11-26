import { useState, type FormEvent } from 'react';
import { send } from '../../services/api';
import { readMember, roles, type StaffMember } from './model';
import { SectionHeading, useCommand } from './ui';

type Fields = Pick<StaffMember, 'username' | 'first_name' | 'last_name' | 'email' | 'department' | 'role'>;
const labels: Record<keyof Fields, string> = {
  username: 'Username', first_name: 'First name', last_name: 'Last name', email: 'Email', department: 'Department', role: 'Role',
};
const empty: Fields = { username: '', first_name: '', last_name: '', email: '', department: '', role: '' };

export function StaffEditor({ member, ownId, onCancel, onSaved }: {
  member?: StaffMember; ownId: number; onCancel: () => void; onSaved: (member: StaffMember) => void;
}) {
  // Explicit allowlist; ID, status, passwords and flags never enter the editable profile values.
  const [fields, setFields] = useState<Fields>(() => member ? {
    username: member.username, first_name: member.first_name, last_name: member.last_name,
    email: member.email, department: member.department, role: member.role,
  } : { ...empty });
  const [newPassword, setNewPassword] = useState(!member);
  const [password, setPassword] = useState('');
  const [repeat, setRepeat] = useState('');
  const [error, setError] = useState('');
  const [reviewed, setReviewed] = useState<Partial<Fields> | null>(null);
  const command = useCommand();
  const own = member?.id === ownId;
  function change(key: keyof Fields, value: string) { setFields(old => ({ ...old, [key]: value })); }

  function review(event: FormEvent) {
    event.preventDefault();
    setError('');
    if (!fields.username.trim() || (!member && !fields.email.trim()) || (!member && !fields.role)) {
      setError('Username, staff email and a role are required for registration.'); return;
    }
    if (newPassword && (password.length < 8 || password.length > 128 || password !== repeat)) {
      setError('Enter matching new passwords between 8 and 128 characters.'); return;
    }
    const changed: Partial<Fields> = {};
    for (const key of Object.keys(labels) as (keyof Fields)[]) {
      if (member && (key === 'username' || (own && key === 'role'))) continue;
      const value = fields[key].trim();
      if (!member || value !== member[key]) changed[key] = value;
    }
    if (!Object.keys(changed).length && !newPassword) { setError('There are no changes to save.'); return; }
    setReviewed(changed);
  }

  function save(event: FormEvent) {
    event.preventDefault();
    if (!reviewed || command.pending) return;
    const body = { ...reviewed, ...(!member ? { is_active: true } : {}), ...(newPassword ? { password } : {}) };
    void command.run(() => (member ? send(`staff/${member.id}/`, 'PATCH', body) : send('staff/', 'POST', body)).then(readMember), result => {
      if (member && member.id !== result.id) {
        throw new Error('No matching account was returned. Check the directory before trying again.');
      }
      setPassword(''); setRepeat('');
      onSaved(result);
    });
  }

  if (reviewed) return <form key="review" className="panel" onSubmit={save} aria-label="Review account">
    <SectionHeading>{member ? 'Review account changes' : 'Review new account'}</SectionHeading>
    <p>{member ? `Changes to ${member.username} (staff #${member.id}). Only the listed changes will be submitted.`
      : 'Check the role and contact details. The new account will be active.'}</p>
    <dl>{(Object.keys(reviewed) as (keyof Fields)[]).map(key => <div key={key}>
      <dt>{labels[key]}</dt><dd>{member && <>{member[key] || '(blank)'} → </>}{reviewed[key] || '(blank)'}</dd>
    </div>)}
      {newPassword && <div><dt>Password</dt><dd>{member ? 'Replace password (not displayed)' : 'Initial password supplied (not displayed)'}</dd></div>}
    </dl>
    {reviewed.role === 'Super Administrator' && <p className="notice">This role grants account administration and full operational access.</p>}
    {member && (newPassword || reviewed.role) && <p className="notice">Changing a role or password requires this account to sign in again.</p>}
    {command.failure && <p className="error" role="alert">{command.failure.message} Check the directory if the result is uncertain.</p>}
    <div className="actions">
      <button className="btn primary" type="submit" disabled={command.pending}>{command.pending ? 'Saving…' : member ? 'Confirm changes' : 'Create account'}</button>
      <button className="btn secondary" type="button" disabled={command.pending}
        onClick={() => { command.clearError(); setReviewed(null); }}>Edit details</button>
      <button className="btn secondary" type="button" disabled={command.pending} onClick={onCancel}>Cancel</button>
    </div>
  </form>;

  return <form key="entry" className="panel" onSubmit={review} aria-label={member ? 'Edit staff account' : 'Register staff account'}>
    <SectionHeading>{member ? `Edit ${member.username}` : 'Register staff account'}</SectionHeading>
    <p className="muted">{member ? `Staff #${member.id} · ${member.is_active ? 'Active' : 'Inactive'}`
      : 'Create a named account. Grant only the role needed for this person’s work.'}</p>
    <div className="form-grid">
      <label className="field">Username<input value={fields.username} required readOnly={!!member} autoComplete="off" maxLength={150}
        onChange={e => change('username', e.target.value)} /></label>
      <label className="field">Email<input type="email" value={fields.email} required={!member || !!member.email} autoComplete="off" maxLength={254}
        onChange={e => change('email', e.target.value)} /></label>
      <label className="field">First name<input value={fields.first_name} maxLength={150} onChange={e => change('first_name', e.target.value)} /></label>
      <label className="field">Last name<input value={fields.last_name} maxLength={150} onChange={e => change('last_name', e.target.value)} /></label>
      <label className="field">Department<input value={fields.department} maxLength={80} onChange={e => change('department', e.target.value)} /></label>
      <label className="field">Role<select value={fields.role} required={!member || !!member.role} disabled={own}
        onChange={e => change('role', e.target.value)}>
        <option value="" disabled>Select a role</option>
        {roles.map(role => <option key={role}>{role}</option>)}
      </select></label>
    </div>
    {own && <p className="muted">Another administrator must change your own role or active status.</p>}
    {member && <label><input type="checkbox" checked={newPassword} onChange={e => {
      setNewPassword(e.target.checked); setPassword(''); setRepeat('');
    }} /> Set a new password</label>}
    {newPassword && <fieldset>
      <legend>{member ? 'Replace password' : 'Initial password'}</legend>
      <p className="muted">Use a unique password. The current password is never displayed.</p>
      <div className="form-grid">
        <label className="field">New password<input type="password" autoComplete="new-password" value={password} required minLength={8} maxLength={128}
          onChange={e => setPassword(e.target.value)} /></label>
        <label className="field">Confirm new password<input type="password" autoComplete="new-password" value={repeat} required minLength={8} maxLength={128}
          onChange={e => setRepeat(e.target.value)} /></label>
      </div>
    </fieldset>}
    {error && <p className="error" role="alert">{error}</p>}
    <div className="actions">
      <button className="btn primary" type="submit">{member ? 'Review changes' : 'Review account'}</button>
      <button className="btn secondary" type="button" onClick={onCancel}>Cancel</button>
    </div>
  </form>;
}

export function StatusConfirmation({ member, onCancel, onSaved }: {
  member: StaffMember; onCancel: () => void; onSaved: (member: StaffMember) => void;
}) {
  const command = useCommand();
  const active = !member.is_active;
  function submit(event: FormEvent) {
    event.preventDefault();
    void command.run(() => send(`staff/${member.id}/`, 'PATCH', { is_active: active }).then(readMember), result => {
      if (result.id !== member.id || result.is_active !== active) throw new Error('Status was not confirmed. Check the directory.');
      onSaved(result);
    });
  }
  return <form className="panel" onSubmit={submit} aria-label="Confirm account status change">
    <SectionHeading>{active ? 'Activate account?' : 'Deactivate account?'}</SectionHeading>
    <p><strong>{member.username}</strong> · Staff #{member.id} · {member.role || 'No assigned role'}</p>
    <p>{active ? 'Sign-in will be enabled for this staff account with its assigned role.'
      : 'Sign-in will be disabled and active sessions ended. The account and its activity history will be retained.'}</p>
    {command.failure && <p className="error" role="alert">{command.failure.message}</p>}
    <div className="actions">
      <button type="button" className="btn secondary" disabled={command.pending} onClick={onCancel}>Cancel</button>
      <button type="submit" className="btn primary" disabled={command.pending}>
        {command.pending ? 'Saving…' : active ? 'Confirm activation' : 'Confirm deactivation'}</button>
    </div>
  </form>;
}
