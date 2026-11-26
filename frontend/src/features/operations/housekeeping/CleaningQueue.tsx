import { useState, type FormEvent } from 'react';
import { send } from '../../../services/api';
import { useCollection, useMutation, useWorkspace } from '../shared/data';
import { AssigneePicker } from '../shared/DirectoryFields';
import { assignedTo, atHotel, statusText, type StaffChoice } from '../shared/format';
import { ConfirmAction, FormActions, LoadState, Notice, Problem, Refresh, SearchBox, Status, StatusFilter } from '../shared/ui';
import { DispatchForm } from './DispatchForm';
import { cleaningStates, nextCleaningWork, roomOf, type CleaningStatus, type CleaningTask } from './model';

interface Rights { manage: boolean; work: boolean; lookupRooms: boolean }

function TaskCard({ task, manage, work, userId, changed }: Omit<Rights, 'lookupRooms'> & {
  task: CleaningTask; userId: number; changed: (message: string) => void;
}) {
  const [assigning, setAssigning] = useState(false);
  const [staff, setStaff] = useState<StaffChoice | null>(null);
  const mutation = useMutation();
  const next = work && (manage || task.assignee === userId) ? nextCleaningWork(task.status) : null;
  const transition = (status: CleaningStatus, assignee?: number) => {
    void mutation.run(() => send<CleaningTask>(`cleaning-tasks/${task.id}/transition/`, 'POST', {
      status, ...(assignee ? { assignee } : {}),
    }), (updated) => changed(`${roomOf(task)} · task #${task.id} is now ${statusText(updated.status).toLowerCase()}.`));
  };
  const assign = (e: FormEvent) => {
    e.preventDefault();
    if (!staff) return mutation.fail('Choose an eligible housekeeper.');
    transition('assigned', staff.id);
  };

  return <article className="ops-record" aria-label={`${roomOf(task)}, cleaning task ${task.id}`}>
    <div className="ops-row-head"><h3>{roomOf(task)} <small className="muted">· Task #{task.id}</small></h3>
      <Status value={task.status} /></div>
    {task.notes && <p className="ops-note">{task.notes}</p>}
    <dl><div><dt>Housekeeper</dt><dd>{assignedTo(task.assignee, task.assignee_name)}</dd></div>
      <div><dt>Opened</dt><dd><time dateTime={task.created_at}>{atHotel(task.created_at)}</time></dd></div></dl>
    {task.status === 'completed' && <p className="muted">Cleaning is complete. Manager inspection is still required.</p>}
    {manage && work && task.status === 'pending' && (assigning ? <form aria-label={`Assign task ${task.id}`} className="ops-fieldset ops-form"
      onSubmit={assign}><AssigneePicker role="Housekeeping Staff" value={staff} change={setStaff} required />
      <FormActions busy={mutation.busy} submit="Save assignment" cancel={() => { setAssigning(false); mutation.fail(''); }} />
    </form> : <div><button type="button" className="btn secondary" onClick={() => setAssigning(true)}>Assign housekeeper</button></div>)}
    {next && <div><button type="button" className="btn primary" disabled={mutation.busy}
      onClick={() => transition(next.target)}>{mutation.busy ? 'Saving…' : next.label}</button></div>}
    {manage && work && task.status === 'completed' && <ConfirmAction label="Record inspection"
      question={`Has ${roomOf(task).toLowerCase()} passed inspection? This records the inspection, not a check-in.`}
      confirm="Mark inspected" busy={mutation.busy} execute={() => transition('inspected')} />}
    <Problem text={mutation.error} focus />
  </article>;
}

export function CleaningQueue({ manage, work, lookupRooms, userId }: Rights & { userId: number }) {
  const [status, setStatus] = useState('');
  const [search, setSearch] = useState('');
  const [creating, setCreating] = useState(false);
  const ws = useWorkspace();
  const list = useCollection<CleaningTask>('cleaning-tasks/', { status, search }, ws.revision);
  return <section className="ops-stack" aria-label="Cleaning tasks">
    <div className="ops-section-head"><div><h2>{manage ? 'Cleaning queue' : 'My cleaning tasks'}</h2>
      <p className="muted">{manage ? 'Dispatch room turnovers and inspect completed work.' : 'Start and complete the room turnovers assigned to you.'}</p></div>
      {manage && lookupRooms && !creating && <button type="button" className="btn primary" onClick={() => {
        ws.clearNotice(); setCreating(true);
      }}>New cleaning task</button>}</div>
    <Notice text={ws.notice} />
    {creating && manage && lookupRooms && <DispatchForm kind="cleaning" cancel={() => setCreating(false)}
      done={(message) => { setCreating(false); ws.changed(message); }} />}
    <div className="panel ops-stack"><div className="toolbar ops-filters">
      <SearchBox label="Find task by room or notes" value={search} change={setSearch} />
      <StatusFilter label="Cleaning status" value={status} change={setStatus} options={cleaningStates} /><Refresh onClick={list.retry} /></div>
      <LoadState list={list} name="cleaning tasks" empty={status || search ? 'No cleaning tasks match these filters.' : 'No cleaning tasks in your queue.'}>
        {(rows) => <div className="ops-records">{rows.map((task) => <TaskCard key={task.id} task={task} manage={manage}
          work={work} userId={userId} changed={ws.changed} />)}</div>}</LoadState>
    </div>
  </section>;
}
