import { useRef, useState } from 'react';
import { categories, kes, nights, readGuests, readRooms, type BookedRoom, type Guest } from './model';
import { query, useRead } from './remote';
import { Feedback, Pager } from './ui';

export type GuestChoice = Pick<Guest, 'id' | 'full_name'> & { reference?: string };
const size = 6;

// Embedded in the reservation form. Enter searches the lookup, never submits a booking.
function LookupSearch({ label, placeholder, apply }: { label: string; placeholder: string; apply: (term: string) => void }) {
  const [text, setText] = useState('');
  return <div className="toolbar"><label className="field">{label}<input type="search" value={text} placeholder={placeholder}
    autoComplete="off" onChange={e => setText(e.target.value)} onKeyDown={e => {
      if (e.key === 'Enter' && !e.nativeEvent.isComposing) { e.preventDefault(); apply(text.trim()); }
    }} /></label><button type="button" className="btn secondary" onClick={() => apply(text.trim())}>{label}</button></div>;
}

export function GuestPicker({ value, change }: { value: GuestChoice | null; change: (guest: GuestChoice) => void }) {
  const [choosing, setChoosing] = useState(!value);
  const changeButton = useRef<HTMLButtonElement>(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const result = useRead(choosing ? query('guests/', { search, page, page_size: size }) : null, readGuests);
  function close() { setChoosing(false); setPage(1); setSearch(''); queueMicrotask(() => changeButton.current?.focus()); }

  return <fieldset className="fd-group"><legend>1 · Primary guest</legend>
    {value && <div className="fd-line"><p><strong>{value.full_name}</strong>{value.reference ? ` · ${value.reference}` : ` · Guest #${value.id}`}</p>
      <button type="button" ref={changeButton} className="btn secondary" onClick={() => choosing ? close() : setChoosing(true)}>
        {choosing ? 'Keep selected guest' : 'Change guest'}</button></div>}
    {choosing && <>
      <LookupSearch label="Search registered guests" placeholder="Guest name or reference" apply={term => { setSearch(term); setPage(1); }} />
      <Feedback result={result} label="Loading registered guests" firstPage={page > 1 ? () => setPage(1) : undefined} />
      {result.data && <>{result.data.results.length ? <ul className="fd-options" aria-label="Matching guests">
        {result.data.results.map(guest => <li key={guest.id} className="fd-line"><span>{guest.full_name} · {guest.reference}</span>
          <button type="button" className="btn secondary" aria-label={`Select ${guest.full_name}, ${guest.reference}`} onClick={() => { change(guest); close(); }}>Select</button></li>)}
      </ul> : <p className="empty">No matching guests. Try a different search or register the guest in the guest directory.</p>}
        <Pager data={result.data} size={size} label="Matching guests" page={page} change={setPage} /></>}
    </>}
  </fieldset>;
}

export function RoomPicker({ arrival, departure, chosen, original, toggle, refreshKey }: {
  arrival: string; departure: string; chosen: BookedRoom[]; original: BookedRoom[];
  toggle: (room: BookedRoom) => void; refreshKey: number;
}) {
  const [page, setPage] = useState(1);
  const [category, setCategory] = useState('');
  const [search, setSearch] = useState('');
  const valid = nights(arrival, departure) > 0;
  const result = useRead(valid ? query('rooms/availability/', { arrival, departure, category, search, page, page_size: size }) : null, readRooms, refreshKey);
  const ids = new Set(chosen.map(room => room.id));
  const removed = original.filter(room => !ids.has(room.id));

  return <fieldset className="fd-group"><legend>3 · Rooms for this stay</legend>
    <h3>Selected rooms ({chosen.length})</h3>
    {chosen.length ? <ul className="fd-picked" aria-label="Selected rooms">{chosen.map(room => <li key={room.id} className="fd-line">
      <span>Room {room.number} · {kes(room.nightly_rate)} / night</span>
      <button type="button" className="btn secondary" aria-label={`Remove room ${room.number}`} onClick={() => toggle(room)}>Remove</button></li>)}</ul>
      : <p className="muted">Select at least one named room from the date search.</p>}
    {!!original.length && <p className="muted">Rooms already on this reservation can be retained even when they do not appear in the general availability search. All requested rooms are checked on save.</p>}
    {!!removed.length && <div className="actions">{removed.map(room => <button type="button" key={room.id} className="btn secondary" onClick={() => toggle(room)}>Restore room {room.number}</button>)}</div>}
    <h3>Available for the selected dates</h3>
    {!valid ? <p className="muted">Enter a valid arrival and departure above to find rooms.</p> : <>
      <label className="field">Room category<select value={category} onChange={e => { setCategory(e.target.value); setPage(1); }}>
        <option value="">All categories</option>{categories.map(name => <option key={name}>{name}</option>)}</select></label>
      <LookupSearch label="Search available rooms" placeholder="Room number or keyword" apply={term => { setSearch(term); setPage(1); }} />
      <Feedback result={result} label="Checking available rooms" firstPage={page > 1 ? () => setPage(1) : undefined} />
      {result.data && <>{result.data.results.length ? <ul className="fd-options" aria-label="Available room choices">{result.data.results.map(room => <li key={room.id}>
        <label className="fd-check"><input type="checkbox" checked={ids.has(room.id)} onChange={() => toggle(original.find(item => item.id === room.id) ?? room)} />
          <span>Room {room.number} · {room.category} · Sleeps {room.capacity}<span className="fd-sub muted">{kes(room.nightly_rate)} / night</span></span></label>
      </li>)}</ul> : <p className="empty">No rooms match this availability search.</p>}
        <Pager data={result.data} size={size} page={page} change={setPage} label="Available rooms" />
        <div><button type="button" className="btn secondary" onClick={result.retry}>Refresh availability</button></div></>}
    </>}
  </fieldset>;
}
