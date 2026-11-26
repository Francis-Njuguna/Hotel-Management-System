import { useState } from 'react';
import { can } from '../../services/api';
import { useSession } from '../../services/session';
import { ActivityLog } from './ActivityLog';
import { StaffEditor, StatusConfirmation } from './StaffEditor';
import { readStaff, type StaffMember } from './model';
import { Pagination, ReadResult, SearchBox, useListing, useRead, type Listing } from './ui';

type StaffView = { kind: 'directory' | 'audit' | 'register' } | { kind: 'edit' | 'status'; member: StaffMember };

function Directory({ listing, ownId, onSelect }: { listing: Listing; ownId: number; onSelect: (view: StaffView) => void }) {
  const request = useRead(`staff/?${listing.params}`, readStaff);
  return <section className="panel" aria-label="Staff directory">
    <div className="toolbar"><h2>Staff directory</h2>
      <button type="button" className="btn primary" onClick={() => onSelect({ kind: 'register' })}>Register staff</button>
    </div>
    <SearchBox label="Search directory" hint="Name, username or department" listing={listing} />
    <ReadResult request={request} label="staff directory">{data => <>
      {data.results.length ? <div className="table-wrap"><table aria-label="Staff accounts">
        <thead><tr><th scope="col">Staff member</th><th scope="col">Role</th><th scope="col">Department</th>
          <th scope="col">Status</th><th scope="col">Actions</th></tr></thead>
        <tbody>{data.results.map(member => {
          const name = [member.first_name, member.last_name].filter(Boolean).join(' ');
          return <tr key={member.id}>
            <th scope="row">{name && <div>{name}</div>}{member.username} {ownId === member.id && <span className="badge">You</span>}</th>
            <td>{member.role || 'Not assigned'}</td><td>{member.department || 'Not assigned'}</td>
            <td><span className="badge">{member.is_active ? 'Active' : 'Inactive'}</span></td>
            <td><div className="actions">
              <button type="button" className="btn secondary" aria-label={`Edit ${member.username}`}
                onClick={() => onSelect({ kind: 'edit', member })}>Edit</button>
              {ownId !== member.id && <button type="button" className="btn secondary"
                aria-label={`${member.is_active ? 'Deactivate' : 'Activate'} ${member.username}`}
                onClick={() => onSelect({ kind: 'status', member })}>{member.is_active ? 'Deactivate' : 'Activate'}</button>}
            </div></td>
          </tr>;
        })}</tbody>
      </table></div> : <p className="empty">{listing.search ? 'No staff match this search.' : 'No staff accounts to display.'}</p>}
      <Pagination label="Accounts" data={data} page={listing.page} onPage={listing.setPage} />
    </>}</ReadResult>
  </section>;
}

function StaffWorkspace({ ownId, manage, audit, refreshSession }: {
  ownId: number; manage: boolean; audit: boolean; refreshSession: () => Promise<void>;
}) {
  const [view, setView] = useState<StaffView>({ kind: manage ? 'directory' : 'audit' });
  const [notice, setNotice] = useState('');
  const directory = useListing();
  const activity = useListing();
  function select(next: StaffView) { setNotice(''); setView(next); }
  function saved(member: StaffMember) {
    if (view.kind === 'register') directory.filter('');
    else if (directory.search) directory.setPage(1);
    setNotice(view.kind === 'status' ? `${member.username} is now ${member.is_active ? 'active' : 'inactive'}.`
      : view.kind === 'register' ? `Account created for ${member.username}.` : `Changes saved for ${member.username}.`);
    setView({ kind: 'directory' });
    if (member.id === ownId) void refreshSession();
  }
  return <>
    {audit && manage && (view.kind === 'directory' || view.kind === 'audit') && <nav className="actions" aria-label="Staff workspace">
      <button type="button" aria-pressed={view.kind === 'directory'} className={`btn ${view.kind === 'directory' ? 'primary' : 'secondary'}`}
        onClick={() => select({ kind: 'directory' })}>Directory</button>
      <button type="button" aria-pressed={view.kind === 'audit'} className={`btn ${view.kind === 'audit' ? 'primary' : 'secondary'}`}
        onClick={() => select({ kind: 'audit' })}>Activity log</button>
    </nav>}
    {notice && <p role="status" className="notice">{notice}</p>}
    {audit && view.kind === 'audit' && <ActivityLog listing={activity} />}
    {manage && view.kind === 'directory' && <Directory ownId={ownId} listing={directory} onSelect={select} />}
    {manage && (view.kind === 'register' || view.kind === 'edit') && <StaffEditor ownId={ownId}
      member={view.kind === 'edit' ? view.member : undefined} onCancel={() => select({ kind: 'directory' })} onSaved={saved} />}
    {manage && view.kind === 'status' && view.member.id !== ownId && <StatusConfirmation member={view.member}
      onCancel={() => select({ kind: 'directory' })} onSaved={saved} />}
  </>;
}

export function StaffPage() {
  const { user, loading, refresh } = useSession();
  const manage = can(user, 'staff.manage');
  const audit = can(user, 'audit.view');
  return <section className="page office-page" aria-labelledby="office-staff-title">
    <header className="page-header"><div><p className="eyebrow">Administration</p>
      <h1 id="office-staff-title">Staff &amp; activity</h1>
      {manage ? <p className="muted">Manage named staff accounts, role assignments and account access.</p>
        : audit && <p className="muted">Review recorded activity without changing staff accounts.</p>}
    </div></header>
    {loading ? <p role="status">Checking access…</p> : user && (manage || audit)
      ? <StaffWorkspace key={`${user.id}:${manage}:${audit}`} ownId={user.id} manage={manage} audit={audit} refreshSession={refresh} />
      : <p className="notice" role="status">You do not have access to staff accounts or activity records.</p>}
  </section>;
}
