import { useState, type FormEvent } from 'react';
import { send } from '../../../services/api';
import { RecordPicker } from '../shared/RecordPicker';
import { useCollection, useMutation, useWorkspace } from '../shared/data';
import { guestLabel, type GuestChoice } from '../shared/format';
import { FormActions, FormHeading, LoadState, Notice, Problem, Refresh, SearchBox, Status } from '../shared/ui';
import { type Vehicle } from './model';

function VehicleForm({ done, cancel }: { done: (s: string) => void; cancel: () => void }) {
  const [guest, setGuest] = useState<GuestChoice | null>(null);
  const [plate, setPlate] = useState('');
  const mutation = useMutation();
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!guest || !plate.trim()) return mutation.fail('Choose a guest and enter the vehicle registration plate.');
    void mutation.run(() => send<Vehicle>('vehicles/', 'POST', { guest: guest.id, plate: plate.trim() }),
      (v) => done(`Vehicle ${v.plate} registered. It can now be selected for a parking allocation.`));
  };
  return <form className="panel ops-form" aria-label="Register vehicle" onSubmit={submit} aria-busy={mutation.busy}>
    <FormHeading hint="Link the vehicle to its guest before assigning a space. Use the guest reference to distinguish similar names.">Register vehicle</FormHeading>
    <div className="form-grid"><RecordPicker label="Registered guest" path="guests/" value={guest} onChange={setGuest}
      describe={guestLabel} noChoice="Choose a guest" empty="No matching guests. Register the guest at the front desk first."
      searchLabel="Find guest by name or reference" />
      <label className="field"><span>Registration plate</span><input required autoCapitalize="characters" spellCheck={false} autoComplete="off"
        value={plate} onChange={(e) => setPlate(e.target.value)} /></label></div>
    <Problem text={mutation.error} focus /><FormActions busy={mutation.busy} submit="Register vehicle" cancel={cancel} />
  </form>;
}

export function VehicleDesk({ register }: { register: boolean }) {
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState('');
  const [allocated, setAllocated] = useState('');
  const ws = useWorkspace();
  const list = useCollection<Vehicle>('vehicles/', { search, allocated }, ws.revision);
  return <section className="ops-stack" aria-label="Registered vehicles"><div className="ops-section-head"><div><h2>Registered vehicles</h2>
    <p className="muted">Find a vehicle by its plate and check the linked guest.</p></div>
    {register && !creating && <button type="button" className="btn primary" onClick={() => { ws.clearNotice(); setCreating(true); }}>Register vehicle</button>}</div>
    <Notice text={ws.notice} />
    {register && creating && <VehicleForm cancel={() => setCreating(false)} done={(s) => { setCreating(false); ws.changed(s); }} />}
    <div className="panel ops-stack"><div className="toolbar ops-filters"><SearchBox label="Find vehicle by plate or guest" value={search} change={setSearch} />
      <label className="field"><span>Parking status</span><select value={allocated} onChange={(e) => setAllocated(e.target.value)}>
        <option value="">All vehicles</option><option value="true">Allocated</option><option value="false">Not allocated</option></select></label>
      <Refresh onClick={list.retry} /></div><LoadState list={list} name="vehicles"
        empty={search || allocated ? 'No vehicles match these filters.' : 'No guest vehicles have been registered.'}>
        {(rows) => <div className="ops-menu-grid">{rows.map((v) => <article key={v.id} className="ops-record" aria-label={`Vehicle ${v.plate}`}>
          <div className="ops-row-head"><h3>{v.plate}</h3>{v.allocated !== undefined && <Status value={v.allocated ? 'allocated' : 'not_allocated'} />}</div>
          <dl><div><dt>Registered guest</dt><dd>{v.guest_name || `Guest #${v.guest}`}</dd></div></dl>
        </article>)}</div>}</LoadState></div>
  </section>;
}
