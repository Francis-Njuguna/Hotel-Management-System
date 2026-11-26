import { useState, type FormEvent } from 'react';
import { send } from '../../../services/api';
import { useCollection, useMutation, useWorkspace } from '../shared/data';
import { FormActions, FormHeading, LoadState, Notice, Problem, Refresh, SearchBox, Status } from '../shared/ui';
import { type Space } from './model';

function SpaceForm({ space, done, cancel }: { space?: Space; done: (s: string) => void; cancel: () => void }) {
  const [code, setCode] = useState(space?.code ?? '');
  const [active, setActive] = useState(space?.is_active ?? true);
  const mutation = useMutation();
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!code.trim()) return mutation.fail('Enter the code displayed at the parking space.');
    const body = { ...(!space || space.code !== code.trim() ? { code: code.trim() } : {}),
      ...(!space || space.is_active !== active ? { is_active: active } : {}) };
    if (!Object.keys(body).length) return done('No parking space changes to save.');
    void mutation.run(() => send<Space>(space ? `parking-spaces/${space.id}/` : 'parking-spaces/', space ? 'PATCH' : 'POST', body),
      (saved) => done(`Parking space ${saved.code} ${space ? 'updated' : 'created'}.`));
  };
  return <form className="panel ops-form" aria-label={space ? 'Edit parking space' : 'New parking space'} onSubmit={submit} aria-busy={mutation.busy}>
    <FormHeading hint="Use the physical bay code so the front desk can identify it during allocation.">{space ? `Edit space ${space.code}` : 'New parking space'}</FormHeading>
    <label className="field"><span>Space code</span><input value={code} required maxLength={24} onChange={(e) => setCode(e.target.value)} /></label>
    <label className="ops-check"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />Space is active</label>
    <small className="muted">An inactive space is retained in history but cannot receive a vehicle.</small>
    <Problem text={mutation.error} focus /><FormActions busy={mutation.busy} submit={space ? 'Save space changes' : 'Create parking space'} cancel={cancel} />
  </form>;
}

export function SpaceDesk({ manage }: { manage: boolean }) {
  const [editing, setEditing] = useState<Space | 'new' | null>(null);
  const [search, setSearch] = useState('');
  const [availability, setAvailability] = useState('');
  const ws = useWorkspace();
  const list = useCollection<Space>('parking-spaces/', { search, available: availability }, ws.revision);
  return <section className="ops-stack" aria-label="Parking spaces"><div className="ops-section-head"><div><h2>Parking spaces</h2>
    <p className="muted">Look up a bay or take a space out of service.</p></div>
    {manage && editing === null && <button type="button" className="btn primary" onClick={() => { ws.clearNotice(); setEditing('new'); }}>New parking space</button>}</div>
    <Notice text={ws.notice} />
    {manage && editing !== null && <SpaceForm key={editing === 'new' ? 'new' : editing.id} space={editing === 'new' ? undefined : editing}
      cancel={() => setEditing(null)} done={(s) => { setEditing(null); ws.changed(s); }} />}
    <div className="panel ops-stack"><div className="toolbar ops-filters"><SearchBox label="Search space code" value={search} change={setSearch} />
      <label className="field"><span>Space availability</span><select value={availability} onChange={(e) => setAvailability(e.target.value)}>
        <option value="">All spaces</option><option value="true">Available for allocation</option><option value="false">Occupied or inactive</option></select></label><Refresh onClick={list.retry} /></div>
      <LoadState list={list} name="parking spaces" empty={search || availability ? 'No spaces match these filters.' : 'No parking spaces have been registered.'}>
        {(rows) => <div className="ops-menu-grid">{rows.map((space) => {
          const state = !space.is_active ? 'inactive' : space.occupied === true || space.available === false ? 'occupied' :
            space.occupied === false || space.available === true ? 'available' : 'active';
          return <article key={space.id} className="ops-record" aria-label={`Space ${space.code}`}>
            <div className="ops-row-head"><h3>Space {space.code}</h3><Status value={state} /></div>
            {manage && !editing && <div><button type="button" className="btn secondary" aria-label={`Edit space ${space.code}`}
              onClick={() => { ws.clearNotice(); setEditing(space); }}>Edit space</button></div>}</article>;
        })}</div>}</LoadState>
    </div>
  </section>;
}
