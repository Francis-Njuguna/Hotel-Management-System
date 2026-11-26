import { useState, type FormEvent } from 'react';
import { AssigneePicker } from '../shared/DirectoryFields';
import { type StaffChoice } from '../shared/format';
import { FormActions, FormHeading, Problem } from '../shared/ui';

export function OrderAssignment({ id, hasAssignee, busy, save, cancel }: {
  id: number; hasAssignee: boolean; busy: boolean; save: (staffId: number | null) => void; cancel: () => void;
}) {
  const [person, setPerson] = useState<StaffChoice | null>(null);
  const [clear, setClear] = useState(false);
  const [error, setError] = useState('');
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (clear) return save(null);
    if (!person) return setError('Choose an active member of the restaurant staff.');
    save(person.id);
  };
  return <form className="ops-fieldset ops-form" onSubmit={submit} aria-label={`Assign order ${id}`} aria-busy={busy}>
    <FormHeading hint="Assignment can change before preparation starts. The ticket stays at its current stage.">Assign order #{id}</FormHeading>
    {hasAssignee && <label className="ops-check"><input type="checkbox" checked={clear} onChange={(e) => { setClear(e.target.checked); setError(''); }} />
      Remove the current assignment</label>}
    {!clear && <AssigneePicker role="Restaurant Staff" value={person} change={(s) => { setPerson(s); setError(''); }} required />}
    <Problem text={error} focus /><FormActions busy={busy} submit={clear ? 'Remove assignment' : 'Save assignment'} cancel={cancel} />
  </form>;
}
