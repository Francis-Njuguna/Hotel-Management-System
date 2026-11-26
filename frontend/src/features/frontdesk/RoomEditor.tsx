import { useRef, useState, type FormEvent } from 'react';
import { send } from '../../services/api';
import { categories, decimalRate, readRoomSaved, type Room, type RoomSaved } from './model';
import { useCommand } from './remote';
import { Dialog, ErrorText } from './ui';

const imageTypes = ['image/jpeg', 'image/png'];

export function RoomEditor({ room, saved, onClose }: { room?: Room; saved: (room: RoomSaved) => void; onClose: () => void }) {
  const [number, setNumber] = useState(room?.number ?? '');
  const [category, setCategory] = useState<Room['category']>(room?.category ?? 'Single');
  const [rate, setRate] = useState(room?.nightly_rate ?? '');
  const [capacity, setCapacity] = useState(room ? String(room.capacity) : '1');
  const [description, setDescription] = useState(room?.description ?? '');
  const [facilities, setFacilities] = useState(room?.facilities.join('\n') ?? '');
  const [active, setActive] = useState(room?.is_active ?? true);
  const [image, setImage] = useState<File | null>(null);
  const [removePhoto, setRemovePhoto] = useState(false);
  const [imageError, setImageError] = useState('');
  const fileInput = useRef<HTMLInputElement>(null);
  const command = useCommand();

  function chooseImage(file: File | null) {
    setImage(null); setImageError('');
    if (!file) return;
    if (!imageTypes.includes(file.type) || !file.size || file.size > 5 * 1024 * 1024) {
      setImageError('Choose a non-empty JPEG or PNG file no larger than 5 MiB.');
      return;
    }
    setImage(file);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (imageError) { fileInput.current?.focus(); return; }
    const nightly_rate = decimalRate(rate);
    if (!number.trim()) { command.setError('Enter a room number or identifier.'); return; }
    if (!nightly_rate) { command.setError('Enter a non-negative nightly rate with up to ten whole digits and two decimal places.'); return; }
    const guests = Number(capacity);
    if (!Number.isSafeInteger(guests) || guests < 1 || guests > 2147483647) { command.setError('Capacity must be a positive whole number within the supported range.'); return; }
    const names = [...new Set(facilities.split(/\r?\n/).map(item => item.trim()).filter(Boolean))];
    if (names.length > 64 || names.some(item => [...item].length > 120)) { command.setError('List up to 64 facilities, each at most 120 characters long.'); return; }
    const values = {
      number: number.trim(), category, nightly_rate, capacity: guests, description: description.trim(),
      facilities: names, is_active: active,
    };
    const fields = (Object.keys(values) as (keyof typeof values)[]).filter(key => !room || JSON.stringify(values[key]) !== JSON.stringify(room[key]));
    if (!fields.length && !image && !removePhoto) { command.setError('Make a change before saving the room.'); return; }
    let body: FormData | Record<string, unknown>;
    if (image) {
      const form = new FormData();
      for (const key of fields) form.append(key, key === 'facilities' ? JSON.stringify(values.facilities) : String(values[key]));
      // No caller-set Content-Type: the browser owns the multipart boundary. The API decodes and re-encodes the file.
      form.append('image', image, image.type === 'image/png' ? 'room.png' : 'room.jpg');
      body = form;
    } else body = { ...Object.fromEntries(fields.map(key => [key, values[key]])), ...(removePhoto && { image: null }) };
    void command.run(() => send(room ? `rooms/${room.id}/` : 'rooms/', room ? 'PATCH' : 'POST', body).then(readRoomSaved), saved);
  }

  return <Dialog title={room ? `Edit room ${room.number}` : 'Add room'} onClose={onClose} busy={command.busy}>
    <form onSubmit={submit} className="fd-form">
      <fieldset disabled={command.busy} className="fd-fields form-grid">
        <label className="field">Room number (required)<input required maxLength={24} value={number} onChange={e => setNumber(e.target.value)} /></label>
        <label className="field">Category<select value={category} onChange={e => setCategory(e.target.value as Room['category'])}>
          {categories.map(value => <option key={value}>{value}</option>)}
        </select></label>
        <label className="field">Nightly rate (KES)<input required inputMode="decimal" placeholder="0.00" value={rate} onChange={e => setRate(e.target.value)} /></label>
        <label className="field">Guest capacity<input required type="number" min="1" max="2147483647" step="1" value={capacity} onChange={e => setCapacity(e.target.value)} /></label>
        <label className="field fd-wide-field">Description<textarea rows={2} value={description} onChange={e => setDescription(e.target.value)} /></label>
        <label className="field fd-wide-field">Facilities (one per line)<textarea rows={3} value={facilities} onChange={e => setFacilities(e.target.value)} /></label>
        <label className="field fd-wide-field">{room?.image ? 'Replace room photo' : 'Room photo'}
          <input type="file" ref={fileInput} accept="image/jpeg,image/png" disabled={removePhoto} aria-invalid={!!imageError}
            aria-describedby={imageError ? 'fd-photo-hint fd-photo-error' : 'fd-photo-hint'} onChange={e => chooseImage(e.target.files?.[0] ?? null)} /></label>
        <p id="fd-photo-hint" className="muted fd-wide-field">Optional still JPEG or PNG, up to 5 MiB and 12 megapixels. {room?.image && 'Leave blank to keep the existing photo.'}</p>
        {imageError && <p id="fd-photo-error" className="error fd-wide-field" role="alert">{imageError}</p>}
        {(image || imageError) && <div className="fd-wide-field"><button type="button" className="btn secondary" onClick={() => {
          if (fileInput.current) fileInput.current.value = ''; chooseImage(null);
        }}>Clear selected photo</button></div>}
        {room?.image && !image && !imageError && <label className="fd-check fd-wide-field"><input type="checkbox" checked={removePhoto} onChange={e => setRemovePhoto(e.target.checked)} />Remove the existing photo when saving this room</label>}
        <label className="fd-check fd-wide-field"><input checked={active} type="checkbox" onChange={e => setActive(e.target.checked)} />Active in the room catalog</label>
        {room?.is_active && !active && <label className="fd-check fd-wide-field"><input type="checkbox" required />I confirm this room should no longer be offered for new bookings.</label>}
      </fieldset>
      <ErrorText>{command.error}</ErrorText>
      <div className="actions"><button type="submit" className="btn primary" disabled={command.busy}>{command.busy ? 'Saving…' : room ? 'Save room changes' : 'Create room'}</button>
        <button type="button" className="btn secondary" disabled={command.busy} onClick={onClose}>Discard</button></div>
    </form>
  </Dialog>;
}
