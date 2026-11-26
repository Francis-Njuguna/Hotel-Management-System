import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Banknote, BedDouble, Bell, CalendarDays, ClipboardCheck, CookingPot, DoorClosed, ReceiptText, Wrench } from 'lucide-react';
import { initials } from '../../app/navigation';
import { EmptyState, FailureState, LoadingState } from '../../app/States';
import { useResource } from '../../app/useResource';
import { Board, StatusBadge } from './Panel';
import { Snapshot, type Indicator } from './Snapshot';
import { amount, calendarDate, decodeInvoices, decodeRepairs, type OrderSummary, type ReservationSummary, type StaffNotification, type TaskSummary } from './model';

type StayFilter = 'All' | 'Arriving today' | 'Leaving today';
const filters: StayFilter[] = ['All', 'Arriving today', 'Leaving today'];

export function ReservationBoard({ rows, date }: { rows: ReservationSummary[]; date: string }) {
  const [filter, setFilter] = useState<StayFilter>('All');
  const visible = rows.filter((row) => filter === 'All' || (row.status !== 'cancelled' && (filter === 'Arriving today' ? row.arrival : row.departure) === date));
  return <Board title="Reservation board" kicker="Front desk" icon={CalendarDays} link="/reservations" linkLabel="View all reservations">
    <div className="brief-filters" role="group" aria-label="Filter this reservation board">{filters.map((item) => <button key={item} type="button"
      aria-pressed={item === filter} onClick={() => setFilter(item)}>{item}</button>)}</div>
    {visible.length ? <div className="table-wrap brief-table-wrap"><table className="brief-stays"><caption className="visually-hidden">Reservations in this briefing, filtered by scheduled stay dates</caption>
      <thead><tr><th scope="col">Guest / booking</th><th scope="col">Stay dates</th><th scope="col">Status</th></tr></thead>
      <tbody>{visible.map((row) => <tr key={row.id}><td><div className="guest-cell"><span className={`guest-avatar avatar-${row.id % 4}`} aria-hidden="true">{initials(row.guest_name)}</span>
        <div><strong>{row.guest_name || `Booking #${row.id}`}</strong><Link className="booking-drilldown" to={`/reservations?reservation=${row.id}`} aria-label={`View history for reservation #${row.id}`}>Reservation #{row.id}</Link></div></div></td>
        <td><div className="stay-dates"><time dateTime={row.arrival}>{calendarDate(row.arrival)}</time><small>to <time dateTime={row.departure}>{calendarDate(row.departure)}</time></small></div></td>
        <td><StatusBadge value={row.status} /></td></tr>)}</tbody></table></div>
      : <EmptyState icon={CalendarDays} title={filter === 'All' ? 'No reservations in this briefing' : 'No matching stays'}>
        {filter === 'All' ? 'Bookings will appear here when included in the property overview.' : 'No bookings in this briefing match the selected day. Choose All to see the rest.'}</EmptyState>}
  </Board>;
}

export function CleaningBoard({ rows }: { rows: TaskSummary[] }) {
  return <Board title="Cleaning queue" kicker="Housekeeping" icon={ClipboardCheck} link="/housekeeping" linkLabel="View cleaning workspace">
    {rows.length ? <ul className="worklist">{rows.map((row) => <li key={row.id}><span className="worklist-icon teal"><BedDouble size={17} aria-hidden="true" /></span>
      <div className="worklist-text"><strong>Room {row.room_number}</strong><small>Cleaning task #{row.id}</small></div><StatusBadge value={row.status} /></li>)}</ul>
      : <EmptyState icon={ClipboardCheck} title="No cleaning tasks in this queue">Tasks available to your account will appear here.</EmptyState>}
  </Board>;
}

export function OrderBoard({ rows }: { rows: OrderSummary[] }) {
  return <Board title="Service orders" kicker="Restaurant" icon={CookingPot} link="/restaurant" linkLabel="View restaurant workspace">
    {rows.length ? <ul className="worklist">{rows.map((row) => <li key={row.id}><span className="worklist-icon amber"><CookingPot size={17} aria-hidden="true" /></span>
      <div className="worklist-text"><strong>Order #{row.id}</strong><small>Restaurant service</small></div><StatusBadge value={row.status} /></li>)}</ul>
      : <EmptyState icon={CookingPot} title="No orders in this queue">Service orders will appear here when included in the shift briefing.</EmptyState>}
  </Board>;
}

export function RepairBoard({ featured = false }: { featured?: boolean }) {
  const result = useResource('maintenance/?status=open&page_size=5', decodeRepairs);
  const metrics: Indicator[] = featured && result.data ? [
    { key: 'open-repairs', label: 'Open work orders', caption: 'In your maintenance scope', path: '/housekeeping', tone: 'blue', icon: Wrench, value: result.data.count.toLocaleString('en-GB') },
    { key: 'blocking-preview', label: 'Blocking requests', caption: 'In the preview below', path: '/housekeeping', tone: 'amber', icon: DoorClosed, value: String(result.data.results.filter((row) => row.blocking).length) },
  ] : [];
  return <><Snapshot items={metrics} /><Board title="Open work orders" kicker="Maintenance" icon={Wrench} link="/housekeeping" linkLabel="View maintenance workspace">
    {result.loading && <LoadingState label="Loading open work orders…" />}
    {result.failed && <FailureState title="Work orders unavailable" message="The maintenance queue could not be loaded." retry={result.reload} />}
    {result.data && (result.data.results.length ? <><p className="board-summary">Showing {result.data.results.length} of {result.data.count} open work orders.</p>
      <ul className="worklist">{result.data.results.map((row) => <li key={row.id}><span className="worklist-icon violet"><DoorClosed size={17} aria-hidden="true" /></span>
        <div className="worklist-text"><strong>{row.room_number ? `Room ${row.room_number}` : `Work order #${row.id}`}</strong><small>{row.description}</small></div>
        <span className="badge">{row.blocking ? 'Room block' : 'Non-blocking'}</span></li>)}</ul></> : <EmptyState icon={Wrench} title="No open work orders">There are no open maintenance requests in your scope.</EmptyState>)}
  </Board></>;
}

export function InvoiceBoard() {
  const result = useResource('invoices/?page_size=5', decodeInvoices);
  return <Board title="Invoice register" kicker="Finance desk" icon={ReceiptText} link="/billing" linkLabel="View billing workspace">
    {result.loading && <LoadingState label="Loading invoice register…" />}
    {result.failed && <FailureState title="Invoices unavailable" message="The invoice register could not be loaded." retry={result.reload} />}
    {result.data && (result.data.results.length ? <ul className="worklist">{result.data.results.map((row) => <li key={row.id}><span className="worklist-icon teal"><Banknote size={17} aria-hidden="true" /></span>
      <div className="worklist-text"><strong>Invoice #{row.id}</strong><small>{row.closed_at ? 'Closed' : 'Open'} · Total KES {amount(row.total)}</small></div>
      <div className="worklist-amount"><small>Balance</small><strong>KES {amount(row.balance)}</strong></div></li>)}</ul>
      : <EmptyState icon={ReceiptText} title="No invoices in the register">When a folio opens or a standalone order is billed, its invoice appears here.</EmptyState>)}
  </Board>;
}

export function MessagePreview({ rows }: { rows: StaffNotification[] }) {
  return <Board title="Your notifications" kicker="Staff inbox" icon={Bell} link="/notifications" linkLabel="View all notifications">
    {rows.length ? <ul className="preview-messages">{rows.slice(0, 3).map((row) => <li key={row.id}><span className={`message-dot ${row.read_at ? '' : 'unread'}`} aria-hidden="true" />
      <div><small>{row.read_at ? 'Read' : 'Unread'}</small><strong>{row.title}</strong><p>{row.message}</p></div></li>)}</ul>
      : <EmptyState icon={Bell} title="No notifications in this briefing">Messages for your staff account will appear here.</EmptyState>}
  </Board>;
}
