import { z } from 'zod';

export const categories = ['Single', 'Double', 'Twin', 'Deluxe', 'Suite', 'Family'] as const;
export const statuses = ['pending', 'confirmed', 'checked_in', 'checked_out', 'cancelled'] as const;
export type BookingStatus = (typeof statuses)[number];

const id = z.number().int().positive();
const decimal = z.string().regex(/^\d+(\.\d{1,2})?$/);
const guest = z.object({ id, reference: z.string(), full_name: z.string(), email: z.string(), phone: z.string() });
const bookedRoom = z.object({ id, number: z.string(), nightly_rate: decimal });
const room = bookedRoom.extend({
  category: z.enum(categories), capacity: z.number().int().positive(), description: z.string(), facilities: z.array(z.string()),
  image: z.string().nullable(), cleanliness: z.enum(['inspected', 'dirty']), is_active: z.boolean(), occupied: z.boolean(), maintenance: z.boolean(),
});
const event = z.object({
  id: id.optional(), status: z.enum(statuses), note: z.string(), actor: id.nullish(), actor_name: z.string().nullish(), created_at: z.string(),
});
const stayDates = z.object({ id, status: z.enum(statuses), arrival: z.iso.date(), departure: z.iso.date() });
const visit = stayDates.extend({ checked_in_at: z.string().nullish(), checked_out_at: z.string().nullish() });
const booking = visit.extend({ guest: id, guest_name: z.string(), rooms: z.array(bookedRoom), events: z.array(event).optional() });
const guestHistory = z.object({
  reservations: z.array(visit), payments: z.array(z.object({ id, amount: decimal, created_at: z.string(), receipt_number: z.string().optional() })).optional(),
});

export type Guest = z.infer<typeof guest>;
export type Room = z.infer<typeof room>;
export type BookedRoom = z.infer<typeof bookedRoom>;
export type Reservation = z.infer<typeof booking>;

const pageOf = <T extends z.ZodType,>(item: T) => z.object({
  count: z.number().int().nonnegative(), next: z.string().nullable(), previous: z.string().nullable(), results: z.array(item),
});

function decoder<T>(schema: z.ZodType<T>, label: string) {
  return (value: unknown): T => {
    const parsed = schema.safeParse(value);
    if (!parsed.success) throw new Error(`The server returned an incomplete or unexpected ${label}. Refresh before continuing.`);
    return parsed.data;
  };
}

export const readGuests = decoder(pageOf(guest), 'guest list');
export const readRooms = decoder(pageOf(room), 'room list');
export const readBookings = decoder(pageOf(booking), 'reservation list');
export const readBooking = decoder(booking, 'reservation');
export const readGuestHistory = decoder(guestHistory, 'guest history');
export const readGuest = decoder(guest, 'guest record');
export const readRoomSaved = decoder(room.pick({ id: true, number: true, category: true }), 'room record');

export type RoomSaved = ReturnType<typeof readRoomSaved>;

export const statusLabel: Record<BookingStatus, string> = {
  pending: 'Pending', confirmed: 'Confirmed', checked_in: 'Checked in',
  checked_out: 'Checked out', cancelled: 'Cancelled',
};

// Keep money out of binary floating point, including when formatting for display.
export function decimalRate(input: string): string | null {
  const value = input.trim();
  if (!/^\d{1,10}(\.\d{1,2})?$/.test(value)) return null;
  const [whole, fraction = ''] = value.split('.');
  return `${whole.replace(/^0+(?=\d)/, '')}.${fraction.padEnd(2, '0')}`;
}

export function kes(value: string): string {
  if (typeof value !== 'string' || !/^\d+(\.\d{1,2})?$/.test(value)) return 'Rate unavailable';
  const [whole, fraction = ''] = value.split('.');
  return `KES ${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${fraction.padEnd(2, '0')}`;
}

const dateFormat = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Africa/Nairobi',
});
const timeFormat = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  timeZone: 'Africa/Nairobi',
});
const dayKey = new Intl.DateTimeFormat('en', { year: 'numeric', month: '2-digit', day: '2-digit', timeZone: 'Africa/Nairobi' });

export function hotelToday(): string {
  const parts = Object.fromEntries(dayKey.formatToParts(new Date()).map(part => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day}`;
}

export function amendable(stay: Reservation, today: string): boolean {
  return (stay.status === 'pending' || stay.status === 'confirmed') && stay.arrival >= today;
}

export function showDate(value: string, withTime = false): string {
  const time = Date.parse(value);
  return Number.isFinite(time) ? (withTime ? timeFormat : dateFormat).format(time) : 'Date unavailable';
}

function dayTime(value: string): number {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return NaN;
  const time = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value ? time : NaN;
}

export function nights(arrival: string, departure: string): number {
  const difference = (dayTime(departure) - dayTime(arrival)) / 86_400_000;
  return difference > 0 ? difference : 0;
}

export function intervalError(arrival: string, departure: string): string {
  if (!arrival || !departure) return 'Enter both an arrival date and a departure date.';
  return nights(arrival, departure) ? '' : 'Departure must be later than arrival.';
}
