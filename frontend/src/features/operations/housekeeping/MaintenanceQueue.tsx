import { useState } from 'react';
import { send } from '../../../services/api';
import { useCollection, useMutation, useWorkspace } from '../shared/data';
import { assignedTo, calendarDay } from '../shared/format';
import { ConfirmAction, LoadState, Notice, Problem, Refresh, SearchBox, Status, StatusFilter } from '../shared/ui';
import { DispatchForm } from './DispatchForm';
import { roomOf, type Maintenance } from './model';

function RepairCard({ job, canResolve, done }: { job: Maintenance; canResolve: boolean; done: (s: string) => void }) {
  const mutation = useMutation();
  return <article className="ops-record" aria-label={`${roomOf(job)}, maintenance request ${job.id}`}>
    <div className="ops-row-head"><h3>{roomOf(job)} <small className="muted">· Request #{job.id}</small></h3><Status value={job.status} /></div>
    <p className="ops-note">{job.description}</p><dl>
      <div><dt>Technician</dt><dd>{assignedTo(job.assignee, job.assignee_name)}</dd></div>
      <div><dt>Work window</dt><dd>{calendarDay(job.start)} to {calendarDay(job.end)} (exclusive)</dd></div>
      <div><dt>Room inventory</dt><dd>{!job.blocking ? 'Non-blocking' : job.status === 'resolved' ? 'Block lifted' : 'Blocked for this window'}</dd></div>
    </dl>
    {canResolve && job.status === 'open' && <ConfirmAction label="Resolve request" confirm="Confirm resolution" busy={mutation.busy}
      question={job.blocking ? 'Mark this repair resolved and release its inventory block?' : 'Has the reported repair been completed?'}
      execute={() => { void mutation.run(() => send<Maintenance>(`maintenance/${job.id}/resolve/`, 'POST', {}),
        () => done(`Maintenance request #${job.id} for ${roomOf(job).toLowerCase()} resolved.`)); }} />}
    <Problem text={mutation.error} focus />
  </article>;
}

export function MaintenanceQueue({ manage, work, lookupRooms, userId }: {
  manage: boolean; work: boolean; lookupRooms: boolean; userId: number;
}) {
  const [status, setStatus] = useState('open');
  const [search, setSearch] = useState('');
  const [blocking, setBlocking] = useState('');
  const [creating, setCreating] = useState(false);
  const ws = useWorkspace();
  const list = useCollection<Maintenance>('maintenance/', { status, search, blocking }, ws.revision);
  return <section className="ops-stack" aria-label="Maintenance requests">
    <div className="ops-section-head"><div><h2>{manage ? 'Maintenance requests' : 'My maintenance requests'}</h2>
      <p className="muted">{manage ? 'Schedule repairs separately from cleaning and track inventory blocks.' : 'Review your repair windows and resolve work when finished.'}</p></div>
      {manage && lookupRooms && !creating && <button type="button" className="btn primary" onClick={() => {
        ws.clearNotice(); setCreating(true);
      }}>New maintenance request</button>}</div><Notice text={ws.notice} />
    {creating && manage && lookupRooms && <DispatchForm kind="maintenance" cancel={() => setCreating(false)}
      done={(message) => { setCreating(false); ws.changed(message); }} />}
    <div className="panel ops-stack"><div className="toolbar ops-filters">
      <SearchBox label="Find request by room or description" value={search} change={setSearch} />
      <StatusFilter label="Maintenance status" options={['open', 'resolved']} value={status} change={setStatus} />
      <label className="field"><span>Inventory impact</span><select value={blocking} onChange={(e) => setBlocking(e.target.value)}>
        <option value="">All requests</option><option value="true">Blocking</option><option value="false">Non-blocking</option></select></label>
      <Refresh onClick={list.retry} /></div>
      <LoadState list={list} name="maintenance requests" empty="No maintenance requests match this view.">
        {(rows) => <div className="ops-records">{rows.map((job) => <RepairCard key={job.id} job={job}
          canResolve={work && (manage || job.assignee === userId)} done={ws.changed} />)}</div>}</LoadState>
    </div>
  </section>;
}
