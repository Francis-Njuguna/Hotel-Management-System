import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { send } from '../../services/api';
import { kes, readGuest, readGuestHistory, showDate, type Guest } from './model';
import { useCommand, useRead } from './remote';
import { Dialog, ErrorText, Feedback, HistoryList, Status } from './ui';

export function GuestEditor({ guest, onClose, saved }: {
  guest?: Guest; onClose: () => void; saved: (guest: Guest) => void;
}) {
  const [name, setName] = useState(guest?.full_name ?? '');
  const [email, setEmail] = useState(guest?.email ?? '');
  const [phone, setPhone] = useState(guest?.phone ?? '');
  const [reference, setReference] = useState(guest?.reference ?? '');
  const command = useCommand();

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) { command.setError('Enter the guest’s full name.'); return; }
    if (guest && !reference.trim()) { command.setError('An existing guest reference cannot be blank.'); return; }
    const profile = { full_name: name.trim(), email: email.trim(), phone: phone.trim(), ...(reference.trim() && { reference: reference.trim() }) };
    const body = guest
      ? Object.fromEntries((Object.keys(profile) as (keyof typeof profile)[])
        .filter(key => guest[key] !== profile[key]).map(key => [key, profile[key]]))
      : profile;
    if (!Object.keys(body).length) { command.setError('Make a change before saving the guest.'); return; }
    void command.run(() => send(guest ? `guests/${guest.id}/` : 'guests/', guest ? 'PATCH' : 'POST', body).then(readGuest), saved);
  }

  return <Dialog title={guest ? 'Edit guest' : 'Register guest'} busy={command.busy} onClose={onClose}>
    <p className="muted">{guest ? 'Update the contact details on this guest record.' : 'Use a new profile only if the guest is not already registered.'}</p>
    <form onSubmit={submit} className="fd-form" autoComplete="off">
      <fieldset disabled={command.busy} className="fd-fields form-grid">
        <label className="field fd-wide-field">Full name (required)
          <input required maxLength={160} value={name} onChange={event => setName(event.target.value)} /></label>
        <label className="field">Email address
          <input type="email" maxLength={254} value={email} onChange={event => setEmail(event.target.value)} /></label>
        <label className="field">Phone number
          <input type="tel" maxLength={32} value={phone} onChange={event => setPhone(event.target.value)} /></label>
        <label className="field fd-wide-field">Guest reference
          <input value={reference} maxLength={64} required={!!guest} aria-describedby="fd-ref-hint" onChange={event => setReference(event.target.value)} /></label>
        <p className="muted fd-wide-field" id="fd-ref-hint">{guest ? 'Use a unique reference. Correcting it updates the same profile and preserves its history.' : 'Leave blank for a hotel-issued reference.'}</p>
      </fieldset>
      <ErrorText>{command.error}</ErrorText>
      <div className="actions"><button type="submit" className="btn primary" disabled={command.busy}>
        {command.busy ? 'Saving…' : guest ? 'Save guest changes' : 'Register guest'}</button>
        <button type="button" className="btn secondary" disabled={command.busy} onClick={onClose}>Discard</button></div>
    </form>
  </Dialog>;
}

export function GuestHistoryDialog({ guest, allowPayments, allowReservations, onClose }: {
  guest: Guest; allowPayments: boolean; allowReservations: boolean; onClose: () => void;
}) {
  const request = useRead(`guests/${guest.id}/history/`, readGuestHistory);
  return <Dialog title="Guest history" onClose={onClose}>
    <p><strong>{guest.full_name}</strong> · {guest.reference}</p>
    <Feedback result={request} label="Loading guest history" />
    {request.data && <>
      <HistoryList title="Reservations" entries={request.data.reservations} empty="No reservations recorded for this guest."
        render={stay => <><div className="fd-line">{allowReservations
          ? <Link to={`/reservations?reservation=${stay.id}`}>Reservation #{stay.id}</Link> : <strong>Reservation #{stay.id}</strong>}<Status status={stay.status} /></div>
          <p>Booked: {showDate(stay.arrival)} – {showDate(stay.departure)}</p>
          {stay.checked_in_at && <p>Actual check-in: {showDate(stay.checked_in_at, true)} (EAT)</p>}
          {stay.checked_out_at && <p>Actual checkout: {showDate(stay.checked_out_at, true)} (EAT)</p>}</>} />
      {allowPayments && Array.isArray(request.data.payments) && <HistoryList title="Payments" entries={request.data.payments}
        empty="No payments recorded for this guest." render={payment => <>
          <div className="fd-line"><strong>{payment.receipt_number ? `Receipt ${payment.receipt_number}` : `Payment #${payment.id}`}</strong>
            <span>{kes(payment.amount)}</span></div><p className="muted">{showDate(payment.created_at, true)} (EAT)</p></>} />}
    </>}
  </Dialog>;
}
