import { useState, type FormEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ReservationEditor } from './ReservationEditor';
import { actionsFor, AmendDialog, GuestBookingDialog, ReservationHistory, TransitionDialog, transitions, type Transition } from './ReservationDialogs';
import { amendable, hotelToday, readBookings, showDate, statuses, statusLabel, type BookingStatus, type Reservation } from './model';
import { query, useRead } from './remote';
import { Access, can, Feedback, Header, Pager, Status, Success } from './ui';

const size = 20;
type Open = { mode: 'create'; guestId?: number } | { mode: 'history' | 'amend'; id: number } | { mode: 'transition'; id: number; action: Transition };

function linkedStatus(params: URLSearchParams): string {
  const status = params.get('status');
  return status && statuses.includes(status as BookingStatus) ? status : '';
}

function positiveId(value: string | null): number | null {
  const id = Number(value);
  return value && /^\d+$/.test(value) && Number.isSafeInteger(id) && id > 0 ? id : null;
}

function linkedDialog(params: URLSearchParams): Open | null {
  const id = positiveId(params.get('reservation'));
  const guestId = positiveId(params.get('new_for'));
  return id ? { mode: 'history', id } : guestId ? { mode: 'create', guestId } : null;
}

export function ReservationsPage() {
  return <Access capability="reservations.view">{user => <BookingDirectory manage={can(user, 'reservations.manage')}
    lookupAccess={can(user, 'guests.view') && can(user, 'rooms.view')} />}</Access>;
}

function BookingDirectory({ manage, lookupAccess }: { manage: boolean; lookupAccess: boolean }) {
  const [term, setTerm] = useState('');
  const [search, setSearch] = useState('');
  const [params, setParams] = useSearchParams();
  const status = linkedStatus(params);
  const [page, setPage] = useState(1);
  const [localDialog, setOpen] = useState<Open | null>(null);
  const open = localDialog ?? linkedDialog(params);
  const [notice, setNotice] = useState('');
  const result = useRead(query('reservations/', { search, status, page, page_size: size }), readBookings);
  const mayEdit = manage && lookupAccess;
  const today = hotelToday();
  function apply(event: FormEvent) { event.preventDefault(); setSearch(term.trim()); setPage(1); }
  function setStatus(value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set('status', value); else next.delete('status');
    setParams(next, { replace: true });
  }
  function clearDialogLink() {
    if (!params.has('reservation') && !params.has('new_for')) return;
    const next = new URLSearchParams(params); next.delete('reservation'); next.delete('new_for'); setParams(next, { replace: true });
  }
  function present(next: Open) { clearDialogLink(); setNotice(''); setOpen(next); }
  function close() { if (open?.mode === 'transition' || open?.mode === 'amend') result.retry(); clearDialogLink(); setOpen(null); }
  function saved(stay: Reservation) {
    const state = statusLabel[stay.status].toLowerCase();
    setNotice(`Reservation #${stay.id} ${open?.mode === 'amend' ? 'amended' : open?.mode === 'create' ? 'created' : 'updated'} for ${stay.guest_name}. Status: ${state}.`);
    clearDialogLink(); setOpen(null); setPage(1); result.retry();
  }

  return <section className="page fd-page">
    <Header title="Reservations" description="Reserve rooms, manage arrivals and departures, and review booking history.">
      {mayEdit && <button className="btn primary" type="button" onClick={() => present({ mode: 'create' })}>New reservation</button>}
    </Header>
    <Success>{notice}</Success>
    <section className="panel" aria-label="Reservation directory">
      <form className="toolbar" role="search" aria-label="Find reservations" onSubmit={apply}>
        <label className="field fd-search">Search reservations<input type="search" placeholder="Guest name or reference" autoComplete="off" value={term} onChange={e => setTerm(e.target.value)} /></label>
        <label className="field">Reservation status<select value={status} onChange={e => { setStatus(e.target.value); setSearch(term.trim()); setPage(1); }}>
          <option value="">All statuses</option>{statuses.map(value => <option key={value} value={value}>{statusLabel[value]}</option>)}</select></label>
        <button type="submit" className="btn secondary">Search</button>
        {(term || search || status) && <button type="button" className="btn secondary" onClick={() => { setSearch(''); setTerm(''); setStatus(''); setPage(1); }}>Clear</button>}
      </form>
      <Feedback result={result} label="Loading reservations" firstPage={page > 1 ? () => setPage(1) : undefined} />
      {result.data && <>{result.data.results.length ? <div className="table-wrap"><table className="fd-table">
        <caption className="fd-sr-only">Reservations and stay actions</caption>
        <thead><tr><th scope="col">Guest / booking</th><th scope="col">Stay dates</th><th scope="col">Rooms</th><th scope="col">Status</th><th scope="col">Actions</th></tr></thead>
        <tbody>{result.data.results.map(stay => <tr key={stay.id}>
          <td><strong>{stay.guest_name}</strong><span className="muted fd-sub">Reservation #{stay.id}</span></td>
          <td><span className="fd-mobile-label" aria-hidden="true">Stay dates</span><time dateTime={stay.arrival}>{showDate(stay.arrival)}</time>
            <span className="fd-sub">to <time dateTime={stay.departure}>{showDate(stay.departure)}</time></span></td>
          <td><span className="fd-mobile-label" aria-hidden="true">Rooms</span>{stay.rooms.map(room => room.number).join(', ')}</td>
          <td><span className="fd-mobile-label" aria-hidden="true">Status</span><Status status={stay.status} /></td>
          <td><div className="actions"><button className="btn secondary" type="button" aria-label={`History for reservation #${stay.id}`} onClick={() => present({ mode: 'history', id: stay.id })}>History</button>
            {mayEdit && amendable(stay, today) && <button type="button" className="btn secondary" aria-label={`Amend reservation #${stay.id}`}
              onClick={() => present({ mode: 'amend', id: stay.id })}>Amend</button>}
            {manage && actionsFor(stay.status).map(action => <button type="button" key={action} className="btn secondary" aria-label={`${transitions[action].label} · #${stay.id}`}
              onClick={() => present({ mode: 'transition', id: stay.id, action })}>{transitions[action].label}</button>)}</div></td>
        </tr>)}</tbody></table></div> : <p className="empty">{status || search ? 'No reservations match these filters.' : 'No reservations have been recorded yet.'}</p>}
        <Pager label="Reservations" size={size} data={result.data} page={page} change={setPage} />
      </>}
    </section>
    {open?.mode === 'create' && mayEdit && (open.guestId ? <GuestBookingDialog key={open.guestId} guestId={open.guestId} onClose={close} saved={saved} />
      : <ReservationEditor onClose={close} saved={saved} />)}
    {open?.mode === 'amend' && mayEdit && <AmendDialog id={open.id} onClose={close} saved={saved} />}
    {open?.mode === 'history' && <ReservationHistory id={open.id} onClose={close} />}
    {open?.mode === 'transition' && manage && <TransitionDialog id={open.id} action={open.action} onClose={close} saved={saved} />}
  </section>;
}
