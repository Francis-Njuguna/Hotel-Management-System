import { useState, type FormEvent } from 'react';
import { RoomCard } from './RoomCard';
import { RoomEditor } from './RoomEditor';
import { categories, intervalError, readRooms, showDate, type Room, type RoomSaved } from './model';
import { query, useRead } from './remote';
import { Access, can, ErrorText, Feedback, Header, Pager, Success } from './ui';

const size = 12;
const allFilters = { search: '', category: '', arrival: '', departure: '', cleanliness: '', occupied: '', maintenance: '', is_active: '' };

export function RoomsPage() {
  return <Access capability="rooms.view">{user => <RoomCatalog manage={can(user, 'rooms.manage')} />}</Access>;
}

function RoomCatalog({ manage }: { manage: boolean }) {
  const [filters, setFilters] = useState(allFilters);
  const [draft, setDraft] = useState(allFilters);
  const [error, setError] = useState('');
  const [page, setPage] = useState(1);
  const [editor, setEditor] = useState<{ room?: Room } | null>(null);
  const [notice, setNotice] = useState('');
  const dated = !!filters.arrival;
  const request = useRead(query(dated ? 'rooms/availability/' : 'rooms/', { ...filters, page, page_size: size }), readRooms);

  function change(key: keyof typeof draft, value: string) { setDraft(current => ({ ...current, [key]: value })); setError(''); }
  function apply(event: FormEvent) {
    event.preventDefault();
    const rangeError = draft.arrival || draft.departure ? intervalError(draft.arrival, draft.departure) : '';
    setError(rangeError);
    if (rangeError) return;
    setFilters({ ...draft, search: draft.search.trim() }); setPage(1); request.retry();
  }
  function reset() { setDraft(allFilters); setFilters(allFilters); setError(''); setPage(1); }
  function edit(room?: Room) { setNotice(''); setEditor({ room }); }
  function saved(room: RoomSaved) {
    setNotice(`Room ${room.number} ${editor?.room ? 'updated' : 'created'} · ${room.category}.`);
    setEditor(null); setPage(1); request.retry();
  }

  return <section className="page fd-page">
    <Header title="Rooms" description="Browse the room catalog or check which rooms are on sale for a stay.">
      {manage && <button type="button" className="btn primary" onClick={() => edit()}>Add room</button>}
    </Header>
    <Success>{notice}</Success>
    <section className="panel" aria-label="Room filters">
      <h2>Find rooms</h2>
      <form className="fd-form" onSubmit={apply}>
        <div className="toolbar"><label className="field fd-search">Search rooms<input type="search" placeholder="Room number or keyword" value={draft.search} onChange={e => change('search', e.target.value)} /></label>
          <label className="field">Category<select value={draft.category} onChange={e => change('category', e.target.value)}>
            <option value="">All categories</option>{categories.map(category => <option key={category}>{category}</option>)}</select></label></div>
        <details className="fd-condition-filters"><summary>Current room condition filters</summary><div className="form-grid">
          <label className="field">Cleaning condition<select value={draft.cleanliness} onChange={e => change('cleanliness', e.target.value)}>
            <option value="">Any condition</option><option value="dirty">Needs cleaning</option><option value="inspected">Inspected</option></select></label>
          <label className="field">Current occupancy<select value={draft.occupied} onChange={e => change('occupied', e.target.value)}>
            <option value="">Any occupancy</option><option value="true">Occupied now</option><option value="false">Unoccupied now</option></select></label>
          <label className="field">Current maintenance<select value={draft.maintenance} onChange={e => change('maintenance', e.target.value)}>
            <option value="">Any maintenance state</option><option value="true">Blocked now</option><option value="false">Not blocked now</option></select></label>
          <label className="field">Catalog status<select value={draft.is_active} onChange={e => change('is_active', e.target.value)}>
            <option value="">Active and inactive</option><option value="true">Active only</option><option value="false">Inactive only</option></select></label>
        </div></details>
        <div className="toolbar"><label className="field">Arrival date<input type="date" value={draft.arrival} aria-describedby="fd-availability-hint" onChange={e => change('arrival', e.target.value)} /></label>
          <label className="field">Departure date<input type="date" value={draft.departure} aria-describedby="fd-availability-hint" onChange={e => change('departure', e.target.value)} /></label>
          <button className="btn primary" type="submit">{draft.arrival || draft.departure ? 'Check availability' : 'Apply filters'}</button>
          <button className="btn secondary" type="button" onClick={reset}>Reset filters</button></div>
        <p id="fd-availability-hint" className="muted">Enter both dates for availability, or leave both blank to browse the catalog. Only active rooms can be offered. The departure night is not included.</p>
        <ErrorText>{error}</ErrorText>
      </form>
    </section>
    <section className="panel" aria-label="Room results">
      <h2>{dated ? 'Available rooms' : 'Room catalog'}</h2>
      <p className="muted">{dated ? `${showDate(filters.arrival)} – ${showDate(filters.departure)}. ` : ''}Current occupancy and cleaning condition are separate from date availability.</p>
      <Feedback result={request} label={dated ? 'Checking room availability' : 'Loading room catalog'} firstPage={page > 1 ? () => setPage(1) : undefined} />
      {request.data && <>
        {request.data.results.length ? <div className="card-grid fd-room-grid">{request.data.results.map(room => <RoomCard key={room.id} room={room}
          edit={manage ? () => edit(room) : undefined} />)}</div> : <p className="empty">{dated ? 'No rooms are available for these dates and filters.' : 'No rooms match the current catalog filters.'}</p>}
        <Pager data={request.data} size={size} label="Rooms" page={page} change={setPage} />
      </>}
    </section>
    {editor && manage && <RoomEditor room={editor.room} saved={saved} onClose={() => setEditor(null)} />}
  </section>;
}
