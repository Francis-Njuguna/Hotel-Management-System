import { useState, type FormEvent } from 'react';
import { send } from '../../../services/api';
import { RecordPicker } from '../shared/RecordPicker';
import { useCollection, useMutation, useWorkspace } from '../shared/data';
import { atHotel } from '../shared/format';
import { ConfirmAction, FormActions, FormHeading, LoadState, Notice, Problem, Refresh, SearchBox, Status } from '../shared/ui';
import { selectableSpace, spaceLabel, spaceOf, vehicleLabel, vehicleOf, type Allocation, type Space, type Vehicle } from './model';

function AllocationForm({ done, cancel }: { done: (s: string) => void; cancel: () => void }) {
  const [space, setSpace] = useState<Space | null>(null);
  const [vehicle, setVehicle] = useState<Vehicle | null>(null);
  const [revision, setRevision] = useState(0);
  const mutation = useMutation();
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!space || !vehicle) return mutation.fail('Choose both a space and a registered vehicle.');
    void mutation.run(() => send<Allocation>('parking-allocations/', 'POST', { space: space.id, vehicle: vehicle.id }),
      () => done(`Space ${space.code} allocated to ${vehicle.plate}.`));
  };
  return <form className="panel ops-form" aria-label="Allocate parking space" onSubmit={submit} aria-busy={mutation.busy}>
    <FormHeading hint="Select a registered vehicle and an available bay. Each vehicle and space can have only one active allocation.">Allocate a space</FormHeading>
    <div className="form-grid"><RecordPicker label="Registered vehicle" path="vehicles/" filters={{ allocated: false }} value={vehicle} onChange={setVehicle}
      describe={vehicleLabel} revision={revision} eligible={(v) => !v.allocated} noChoice="Choose a vehicle" searchLabel="Find vehicle by plate"
      empty="No matching vehicles on this page. Use Vehicles to register one." />
      <RecordPicker label="Available parking space" path="parking-spaces/" filters={{ available: true }} revision={revision}
        value={space} onChange={setSpace} describe={spaceLabel} eligible={selectableSpace} noChoice="Choose a space" searchLabel="Find space by code"
        empty="No available spaces on this page. Check other pages, add a space or release a completed allocation." /></div>
    <Problem text={mutation.error} focus />{mutation.error && <div><button type="button" className="btn secondary" onClick={() => {
      setSpace(null); setVehicle(null); setRevision((r) => r + 1);
    }}>Reload available choices</button></div>}
    <FormActions busy={mutation.busy} submit="Allocate space" cancel={cancel} />
  </form>;
}

function AllocationCard({ row, manage, done }: { row: Allocation; manage: boolean; done: (s: string) => void }) {
  const mutation = useMutation();
  const active = !row.ended_at;
  return <article className="ops-record" aria-label={`Allocation ${row.id}`}>
    <div className="ops-row-head"><h3>{spaceOf(row)} <small className="muted">· Allocation #{row.id}</small></h3>
      <Status value={active ? 'active' : 'released'} /></div>
    <dl><div><dt>Vehicle</dt><dd>{vehicleOf(row)}</dd></div>
      {row.guest && <div><dt>Guest</dt><dd>{row.guest_name || `Guest #${row.guest}`}</dd></div>}<div><dt>Allocated</dt>
      <dd><time dateTime={row.started_at}>{atHotel(row.started_at)}</time></dd></div>
      {row.ended_at && <div><dt>Released</dt><dd><time dateTime={row.ended_at}>{atHotel(row.ended_at)}</time></dd></div>}</dl>
    {manage && active && <ConfirmAction label="Release space" confirm="Confirm release" busy={mutation.busy}
      question={`Has ${vehicleOf(row)} left ${spaceOf(row).toLowerCase()}? Releasing closes this allocation and retains it in history.`}
      execute={() => { void mutation.run(() => send<Allocation>(`parking-allocations/${row.id}/release/`, 'POST', {}),
        () => done(`${spaceOf(row)} released. The completed allocation is in parking history.`)); }} />}
    <Problem text={mutation.error} focus />
  </article>;
}

export function AllocationDesk({ manage }: { manage: boolean }) {
  const [creating, setCreating] = useState(false);
  const [view, setView] = useState('active');
  const [search, setSearch] = useState('');
  const ws = useWorkspace();
  const list = useCollection<Allocation>('parking-allocations/', { status: view, search }, ws.revision);
  return <section className="ops-stack" aria-label="Parking allocations"><div className="ops-section-head"><div><h2>Parking allocations</h2>
    <p className="muted">Assign a bay on arrival, release it on departure and find past allocations.</p></div>
    {manage && !creating && <button type="button" className="btn primary" onClick={() => { ws.clearNotice(); setCreating(true); }}>Allocate a space</button>}</div>
    <Notice text={ws.notice} />
    {manage && creating && <AllocationForm cancel={() => setCreating(false)} done={(s) => { setCreating(false); ws.changed(s); }} />}
    <div className="panel ops-stack"><div className="toolbar ops-filters"><label className="field"><span>Allocation view</span>
      <select value={view} onChange={(e) => setView(e.target.value)}><option value="active">Currently parked</option><option value="released">Released history</option>
        <option value="">Entire history</option></select></label><SearchBox label="Find allocation by plate or space" value={search} change={setSearch} />
      <Refresh onClick={list.retry} /></div>
      <LoadState list={list} name="parking allocations" empty={search ? 'No allocations match your search.' :
        view === 'active' ? 'No vehicles are currently parked.' : 'No parking history in this view.'}>
        {(rows) => <div className="ops-records">{rows.map((row) => <AllocationCard key={row.id} row={row} manage={manage} done={ws.changed} />)}</div>}</LoadState>
    </div>
  </section>;
}
