const money = new Intl.NumberFormat('en-KE', {
  style: 'currency', currency: 'KES', currencyDisplay: 'code', minimumFractionDigits: 2,
});
const localTime = new Intl.DateTimeFormat('en-KE', {
  day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  hour12: false, timeZone: 'Africa/Nairobi',
});
const day = new Intl.DateTimeFormat('en-KE', {
  day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC',
});

export function kes(value: string | number): string {
  const n = Number(value);
  return value !== '' && Number.isFinite(n) ? money.format(n) : 'Price not available';
}

export function atHotel(value: string): string {
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? `${localTime.format(date)} EAT` : 'Time not available';
}

export function calendarDay(value: string): string {
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isFinite(date.getTime()) ? day.format(date) : value;
}

export function statusText(code: string): string {
  const text = code.replace(/_/g, ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export interface RoomChoice { id: number; number: string; category?: string; is_active?: boolean }
export interface StaffChoice { id: number; full_name: string; username: string }
export interface GuestChoice { id: number; full_name: string; reference: string }
export const roomLabel = (r: RoomChoice) => `Room ${r.number}${r.category ? ` · ${r.category}` : ''}`;
export const personLabel = (s: StaffChoice) => s.full_name || s.username;
export const guestLabel = (g: GuestChoice) => `${g.full_name} · ${g.reference}`;
export const assignedTo = (id: number | null, name?: string | null) =>
  !id ? 'Unassigned' : name || `Staff #${id}`;
