import { send } from '../../services/api';
import { ReservationEditor } from './ReservationEditor';
import { amendable, hotelToday, kes, readBooking, readGuest, showDate, statusLabel, type BookingStatus, type Reservation } from './model';
import { isConflict, useCommand, useRead } from './remote';
import { Dialog, ErrorText, Feedback, HistoryList, Status } from './ui';

export const transitions = {
  confirm: { label: 'Confirm reservation', description: 'Reserve all named rooms for the requested nights. If any room conflicts, none of the rooms will be confirmed.' },
  cancel: { label: 'Cancel reservation', description: 'Cancel this entire booking and release any rooms held by it. The reservation and its history are retained.' },
  check_in: { label: 'Check in', description: 'Admit the guest to every booked room and open the folio at the agreed rates. The system will check the dates, occupancy, maintenance and inspection of each room.' },
  check_out: { label: 'Check out', description: 'End the stay for all booked rooms, close the folio and request cleaning. Checkout requires a settled balance and no open restaurant orders; it does not record a payment.' },
} as const;
export type Transition = keyof typeof transitions;

export function actionsFor(status: BookingStatus): Transition[] {
  if (status === 'pending') return ['confirm', 'cancel'];
  if (status === 'confirmed') return ['check_in', 'cancel'];
  if (status === 'checked_in') return ['check_out'];
  return [];
}

function StaySummary({ stay }: { stay: Reservation }) {
  return <div className="fd-summary fd-stack"><div className="fd-line"><strong>{stay.guest_name}</strong><Status status={stay.status} /></div>
    <p>{showDate(stay.arrival)} – {showDate(stay.departure)}</p>
    <ul className="fd-facts" aria-label="Booked rooms and agreed rates">{stay.rooms.map(room => <li key={room.id}>
      Room {room.number} · {kes(room.nightly_rate)} / night</li>)}</ul>
    {stay.checked_in_at && <p>Actual check-in: {showDate(stay.checked_in_at, true)} (EAT)</p>}
    {stay.checked_out_at && <p>Actual checkout: {showDate(stay.checked_out_at, true)} (EAT)</p>}
  </div>;
}

export function ReservationHistory({ id, onClose }: { id: number; onClose: () => void }) {
  const result = useRead(`reservations/${id}/`, readBooking);
  return <Dialog title={`Reservation #${id} history`} onClose={onClose}>
    <Feedback result={result} label="Loading reservation history" />
    {result.data && <><StaySummary stay={result.data} />
      {Array.isArray(result.data.events) ? <HistoryList title="Reservation events" entries={result.data.events} empty="No events recorded for this reservation."
        render={event => <><div className="fd-line"><Status status={event.status} /><time dateTime={event.created_at}>{showDate(event.created_at, true)} (EAT)</time></div>
          {event.note && <p>{event.note}</p>}{(event.actor_name || event.actor) && <p className="muted">Recorded by {event.actor_name || `staff #${event.actor}`}</p>}</>} />
        : <p className="muted">Event history was not included in this response.</p>}
    </>}
  </Dialog>;
}

export function GuestBookingDialog({ guestId, saved, onClose }: { guestId: number; saved: (stay: Reservation) => void; onClose: () => void }) {
  const result = useRead(`guests/${guestId}/`, readGuest);
  if (result.data) return <ReservationEditor primaryGuest={result.data} saved={saved} onClose={onClose} />;
  return <Dialog title="New reservation" onClose={onClose}><Feedback result={result} label="Loading the selected guest" /></Dialog>;
}

// Do not populate the amendment form with an old list snapshot.
export function AmendDialog({ id, onClose, saved }: { id: number; onClose: () => void; saved: (stay: Reservation) => void }) {
  const result = useRead(`reservations/${id}/`, readBooking);
  if (result.data && amendable(result.data, hotelToday())) {
    return <ReservationEditor reservation={result.data} saved={saved} onClose={onClose} />;
  }
  return <Dialog title={`Amend reservation #${id}`} onClose={onClose}>
    <Feedback result={result} label="Loading current reservation" />
    {result.data && <p role="status">This booking cannot be amended. Only a pending or confirmed booking whose scheduled arrival has not passed may be changed.</p>}
  </Dialog>;
}

export function TransitionDialog({ id, action, saved, onClose }: {
  id: number; action: Transition; saved: (stay: Reservation) => void; onClose: () => void;
}) {
  const result = useRead(`reservations/${id}/`, readBooking);
  const command = useCommand();
  const { label, description } = transitions[action];
  const eligible = !!result.data && actionsFor(result.data.status).includes(action);
  function perform() {
    if (!eligible) return;
    void command.run(() => send(`reservations/${id}/${action}/`, 'POST', {}).then(readBooking), saved,
      problem => { if (isConflict(problem)) result.retry(); });
  }
  return <Dialog title={`${label} · #${id}`} onClose={onClose} busy={command.busy}>
    <Feedback result={result} label="Checking current reservation" />
    {result.data && <><StaySummary stay={result.data} /><p>{eligible ? description : `This booking is now ${statusLabel[result.data.status].toLowerCase()}; this action is no longer available.`}</p></>}
    <ErrorText>{command.error}</ErrorText>
    <div className="actions"><button className="btn secondary" type="button" disabled={command.busy} onClick={onClose}>Go back</button>
      <button className="btn primary" type="button" disabled={!eligible || command.busy} onClick={perform}>{command.busy ? 'Submitting…' : label}</button></div>
  </Dialog>;
}
