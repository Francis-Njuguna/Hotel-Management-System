import { useState, type FormEvent } from 'react';
import { send } from '../../services/api';
import { GuestPicker, RoomPicker, type GuestChoice } from './Lookups';
import { hotelToday, intervalError, nights, readBooking, type BookedRoom, type Reservation } from './model';
import { isConflict, useCommand } from './remote';
import { Dialog, ErrorText } from './ui';

export function ReservationEditor({ reservation, primaryGuest, saved, onClose }: {
  reservation?: Reservation; primaryGuest?: GuestChoice; saved: (reservation: Reservation) => void; onClose: () => void;
}) {
  const [guest, setGuest] = useState<GuestChoice | null>(reservation ? { id: reservation.guest, full_name: reservation.guest_name } : primaryGuest ?? null);
  const [arrival, setArrival] = useState(reservation?.arrival ?? '');
  const [departure, setDeparture] = useState(reservation?.departure ?? '');
  const [chosen, setChosen] = useState<BookedRoom[]>(reservation?.rooms ?? []);
  const [confirm, setConfirm] = useState(true);
  const [inventoryVersion, setInventoryVersion] = useState(0);
  const [info, setInfo] = useState('');
  const command = useCommand();
  const duration = nights(arrival, departure);
  const badInterval = !!(arrival && departure && !duration);

  function changeDate(side: 'arrival' | 'departure', value: string) {
    const originalIds = new Set(reservation?.rooms.map(room => room.id));
    if (chosen.some(room => !originalIds.has(room.id))) {
      setChosen(chosen.filter(room => originalIds.has(room.id)));
      setInfo('Dates changed. Select new rooms again for this interval.');
    } else setInfo('');
    command.setError('');
    if (side === 'arrival') setArrival(value); else setDeparture(value);
  }
  function toggle(room: BookedRoom) {
    setChosen(current => current.some(item => item.id === room.id) ? current.filter(item => item.id !== room.id)
      : [...current, { id: room.id, number: room.number, nightly_rate: room.nightly_rate }]);
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!guest) { command.setError('Select a registered primary guest.'); return; }
    const error = intervalError(arrival, departure);
    if (error) { command.setError(error); return; }
    if (!chosen.length) { command.setError('Select at least one room for this stay.'); return; }
    setInfo('');
    const room_ids = chosen.map(room => room.id);
    const originalIds = new Set(reservation?.rooms.map(room => room.id));
    const body = reservation ? {
      ...(guest.id !== reservation.guest && { guest: guest.id }), ...(arrival !== reservation.arrival && { arrival }),
      ...(departure !== reservation.departure && { departure }),
      ...((originalIds.size !== room_ids.length || room_ids.some(id => !originalIds.has(id))) && { room_ids }),
    } : { guest: guest.id, arrival, departure, room_ids, confirm };
    if (!Object.keys(body).length) { command.setError('Make a change before saving the amendment.'); return; }
    void command.run(() => send(reservation ? `reservations/${reservation.id}/` : 'reservations/', reservation ? 'PATCH' : 'POST', body).then(readBooking), saved, problem => {
      if (isConflict(problem)) {
        setInventoryVersion(value => value + 1);
        setInfo('Booking conflict. Availability is being rechecked. Your choices are retained; review the dates and rooms before retrying.');
      }
    });
  }

  return <Dialog wide title={reservation ? `Amend reservation #${reservation.id}` : 'New reservation'} busy={command.busy} onClose={onClose}>
    <form className="fd-form" onSubmit={submit}>
      <fieldset className="fd-fields" disabled={command.busy}>
        <GuestPicker value={guest} change={setGuest} />
        <fieldset className="fd-group"><legend>2 · Stay dates</legend>
          <div className="form-grid"><label className="field">Arrival date<input type="date" required min={reservation ? hotelToday() : undefined} value={arrival} onChange={e => changeDate('arrival', e.target.value)} /></label>
            <label className="field">Departure date<input type="date" required value={departure} aria-invalid={badInterval} aria-describedby="fd-stay-dates"
              onChange={e => changeDate('departure', e.target.value)} /></label></div>
          <p id="fd-stay-dates" className={badInterval ? 'error' : 'muted'} aria-live="polite">{badInterval ? intervalError(arrival, departure)
            : duration ? `${duration} ${duration === 1 ? 'night' : 'nights'} · The departure night is not included.` : 'All rooms share the same arrival and departure.'}</p>
        </fieldset>
        <RoomPicker key={`${arrival}/${departure}`} arrival={arrival} departure={departure} chosen={chosen} original={reservation?.rooms ?? []}
          toggle={toggle} refreshKey={inventoryVersion} />
        {!reservation && <label className="field">Booking mode<select value={confirm ? 'confirmed' : 'pending'} onChange={e => setConfirm(e.target.value === 'confirmed')}>
          <option value="confirmed">Confirm and reserve the rooms</option><option value="pending">Save pending without holding rooms</option></select></label>}
        <p className="muted">{reservation ? 'An amendment applies to the whole booking. The existing reservation remains in place if the change is rejected.'
          : confirm ? 'Confirmation reserves all selected rooms together, subject to a final availability check.' : 'Pending reservations do not hold inventory. Confirm later from the reservations list.'}</p>
      </fieldset>
      <ErrorText>{command.error}</ErrorText><div role="status" aria-live="polite">{info && <p className="notice">{info}</p>}</div>
      <div className="actions"><button type="submit" className="btn primary" disabled={command.busy}>
        {command.busy ? 'Saving…' : reservation ? 'Save amendment' : confirm ? 'Create confirmed reservation' : 'Save pending reservation'}</button>
        <button type="button" className="btn secondary" onClick={onClose} disabled={command.busy}>Discard</button></div>
    </form>
  </Dialog>;
}
