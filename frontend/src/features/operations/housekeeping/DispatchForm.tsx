import { useId, useState, type FormEvent } from 'react';
import { send } from '../../../services/api';
import { AssigneePicker, RoomPicker } from '../shared/DirectoryFields';
import { useMutation } from '../shared/data';
import { type RoomChoice, type StaffChoice } from '../shared/format';
import { FormActions, FormHeading, Problem } from '../shared/ui';
import { type CleaningTask, type Maintenance } from './model';

interface Props { kind: 'cleaning' | 'maintenance'; done: (message: string) => void; cancel: () => void }

export function DispatchForm({ kind, done, cancel }: Props) {
  const cleaning = kind === 'cleaning';
  const [room, setRoom] = useState<RoomChoice | null>(null);
  const [assignee, setAssignee] = useState<StaffChoice | null>(null);
  const [note, setNote] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [blocking, setBlocking] = useState(false);
  const mutation = useMutation();
  const hint = useId();
  const invalidEnd = Boolean(start && end && end <= start);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!room) return mutation.fail('Choose a room before dispatching work.');
    const assigned = assignee ? { assignee: assignee.id } : {};
    if (cleaning) {
      void mutation.run(() => send<CleaningTask>('cleaning-tasks/', 'POST', {
        room: room.id, notes: note.trim(), ...assigned,
      }), (task) => done(`Cleaning task #${task.id} created for room ${room.number}.`));
    } else {
      if (!note.trim()) return mutation.fail('Describe the repair that is needed.');
      if (!start || !end || end <= start) return mutation.fail('The end date must be after the start date.');
      void mutation.run(() => send<Maintenance>('maintenance/', 'POST', {
        room: room.id, description: note.trim(), start, end, blocking, ...assigned,
      }), (job) => done(`Maintenance request #${job.id} opened for room ${room.number}.`));
    }
  };

  return <form className="panel ops-form" aria-label={cleaning ? 'New cleaning task' : 'New maintenance request'}
    onSubmit={submit} aria-busy={mutation.busy}>
    <FormHeading hint={cleaning ? 'Opening a cleaning task marks the room dirty. Assign a housekeeper now or dispatch it from the queue later.' :
      'Choose the room, work window and technician. Block the room only if it must be taken out of inventory.'}>
      {cleaning ? 'New cleaning task' : 'New maintenance request'}</FormHeading>
    <div className="form-grid"><RoomPicker value={room} change={setRoom} />
      <AssigneePicker role={cleaning ? 'Housekeeping Staff' : 'Maintenance Staff'} value={assignee} change={setAssignee} />
    </div>
    <label className="field"><span>{cleaning ? 'Cleaning notes (optional)' : 'Repair description'}</span>
      <textarea rows={3} required={!cleaning} value={note} onChange={(e) => setNote(e.target.value)} /></label>
    {!cleaning && <fieldset className="ops-fieldset ops-stack"><legend>Work window</legend><div className="form-grid">
      <label className="field"><span>Start date</span><input type="date" required value={start}
        onChange={(e) => setStart(e.target.value)} /></label>
      <label className="field"><span>End date (exclusive)</span><input type="date" required value={end}
        aria-invalid={invalidEnd || undefined} aria-describedby={invalidEnd ? `${hint}-error ${hint}` : hint} onChange={(e) => setEnd(e.target.value)} />
        {invalidEnd && <small id={`${hint}-error`} className="field-error">Choose an end date after the start date.</small>}</label></div>
      <label className="ops-check"><input type="checkbox" checked={blocking} onChange={(e) => setBlocking(e.target.checked)} />
        Block room inventory for these nights</label>
      <small id={hint} className="muted">The window includes the start date but not the end date. A blocking request cannot overlap an existing room commitment.</small>
    </fieldset>}
    <Problem text={mutation.error} focus /><FormActions busy={mutation.busy}
      submit={cleaning ? 'Create cleaning task' : 'Open maintenance request'} cancel={cancel} />
  </form>;
}
