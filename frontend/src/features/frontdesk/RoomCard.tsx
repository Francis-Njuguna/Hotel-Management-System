import { useState } from 'react';
import { kes, type Room } from './model';

function RoomPhoto({ image, number }: Pick<Room, 'image' | 'number'>) {
  const [failed, setFailed] = useState(false);
  let url: URL | null = null;
  if (image) {
    try { url = new URL(image, window.location.origin); } catch { /* Unusable media URL. */ }
  }
  if (failed || !url || url.origin !== window.location.origin || !/^https?:$/.test(url.protocol)) {
    return <div className="fd-no-photo">{image ? 'Room photo unavailable' : 'No room photo'}</div>;
  }
  return <img src={url.href} alt={`Room ${number}`} loading="lazy" decoding="async" onError={() => setFailed(true)} />;
}

export function RoomCard({ room, edit }: { room: Room; edit?: () => void }) {
  return <article className="fd-room-card" aria-labelledby={`fd-room-${room.id}`}>
    <RoomPhoto key={room.image} image={room.image} number={room.number} />
    <div className="fd-room-body">
      <div className="fd-line"><h3 id={`fd-room-${room.id}`}>Room {room.number}</h3><span className="badge">{room.is_active ? 'Active' : 'Inactive'}</span></div>
      <p>{room.category} · Sleeps {room.capacity}</p>
      <p><strong>{kes(room.nightly_rate)}</strong> / night</p>
      {room.description && <p>{room.description}</p>}
      <p className="muted">Facilities: {room.facilities.length ? room.facilities.join(' · ') : 'None listed'}</p>
      <ul className="fd-facts" aria-label="Current room condition">
        <li>{room.occupied ? 'Occupied now' : 'Unoccupied now'}</li>
        <li>{room.cleanliness === 'inspected' ? 'Inspected' : 'Needs cleaning'}</li>
        <li>{room.maintenance ? 'Maintenance block' : 'No current block'}</li>
      </ul>
      {edit && <div><button className="btn secondary" type="button" onClick={edit} aria-label={`Edit room ${room.number}`}>Edit room</button></div>}
    </div>
  </article>;
}
