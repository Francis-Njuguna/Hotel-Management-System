import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { GuestEditor, GuestHistoryDialog } from './GuestDialogs';
import { readGuests, type Guest } from './model';
import { query, useRead } from './remote';
import { Access, can, Feedback, Header, Pager, Success } from './ui';

type Open = { mode: 'edit'; guest?: Guest } | { mode: 'history'; guest: Guest };
const size = 20;

export function GuestsPage() {
  return <Access capability="guests.view">{user => <GuestDirectory manage={can(user, 'guests.manage')}
    allowPayments={can(user, 'billing.view')} allowReservations={can(user, 'reservations.view')}
    allowBooking={can(user, 'reservations.view') && can(user, 'reservations.manage') && can(user, 'rooms.view')} />}</Access>;
}

function GuestDirectory({ manage, allowPayments, allowReservations, allowBooking }: {
  manage: boolean; allowPayments: boolean; allowReservations: boolean; allowBooking: boolean;
}) {
  const [term, setTerm] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<Open | null>(null);
  const [success, setSuccess] = useState('');
  const result = useRead(query('guests/', { search, page, page_size: size }), readGuests);
  function apply(event: FormEvent) {
    event.preventDefault(); setSearch(term.trim()); setPage(1);
  }
  function present(next: Open) { setSuccess(''); setOpen(next); }
  function saved(guest: Guest) {
    setSuccess(`${guest.full_name} (${guest.reference}) ${open?.mode === 'edit' && open.guest ? 'updated' : 'registered'}.`);
    setOpen(null); setPage(1); result.retry();
  }

  return <section className="page fd-page">
    <Header title="Guests" description="Find a guest profile, update contact details or review past visits.">
      {manage && <button type="button" className="btn primary" onClick={() => present({ mode: 'edit' })}>Register guest</button>}
    </Header>
    <Success>{success}</Success>
    <section className="panel" aria-label="Guest directory">
      <form className="toolbar" role="search" aria-label="Guest directory search" onSubmit={apply}>
        <label className="field fd-search">Search guests
          <input type="search" autoComplete="off" placeholder="Name, reference or contact" value={term} onChange={event => setTerm(event.target.value)} /></label>
        <button className="btn secondary" type="submit">Search</button>
        {(term || search) && <button className="btn secondary" type="button" onClick={() => { setTerm(''); setSearch(''); setPage(1); }}>Clear</button>}
      </form>
      <Feedback result={result} label="Loading guests" firstPage={page > 1 ? () => setPage(1) : undefined} />
      {result.data && <>
        {result.data.results.length ? <div className="table-wrap"><table className="fd-table">
          <caption className="fd-sr-only">Registered guests</caption>
          <thead><tr><th scope="col">Guest</th><th scope="col">Email</th><th scope="col">Phone</th><th scope="col">Actions</th></tr></thead>
          <tbody>{result.data.results.map(guest => <tr key={guest.id}>
            <td><strong>{guest.full_name}</strong><span className="muted fd-sub">{guest.reference}</span></td>
            <td><span className="fd-mobile-label" aria-hidden="true">Email</span>{guest.email || 'Not provided'}</td>
            <td><span className="fd-mobile-label" aria-hidden="true">Phone</span>{guest.phone || 'Not provided'}</td>
            <td><div className="actions"><button type="button" className="btn secondary" aria-label={`History for ${guest.full_name}, ${guest.reference}`}
              onClick={() => present({ mode: 'history', guest })}>History</button>
              {manage && <button type="button" className="btn secondary" aria-label={`Edit ${guest.full_name}, ${guest.reference}`}
                onClick={() => present({ mode: 'edit', guest })}>Edit</button>}
              {allowBooking && <Link className="btn secondary" to={`/reservations?new_for=${guest.id}`}
                aria-label={`Book a stay for ${guest.full_name}, ${guest.reference}`}>Book stay</Link>}</div></td>
          </tr>)}</tbody></table></div> : <p className="empty">{search ? 'No guests match this search. Try another name or reference.' : 'No guest profiles yet.'}</p>}
        <Pager label="Guests" data={result.data} page={page} size={size} change={setPage} />
      </>}
    </section>
    {open?.mode === 'edit' && manage && <GuestEditor guest={open.guest} saved={saved} onClose={() => setOpen(null)} />}
    {open?.mode === 'history' && <GuestHistoryDialog guest={open.guest} allowPayments={allowPayments} allowReservations={allowReservations} onClose={() => setOpen(null)} />}
  </section>;
}
