import { z } from 'zod';

const count = z.number().int().nonnegative();
const identifier = z.number().int().positive();
const day = z.iso.date();
const decimal = z.union([z.string(), z.number().nonnegative().transform(String)]).pipe(z.string().regex(/^\d+(?:\.\d{1,2})?$/));
const status = z.string().min(1);
const reservation = z.object({ id: identifier, guest_name: z.string(), arrival: day, departure: day, status });
const task = z.object({ id: identifier, room_number: z.union([z.string(), z.number()]), status });
const order = z.object({ id: identifier, status });
const notification = z.object({ id: identifier, title: z.string(), message: z.string(), read_at: z.string().nullable(), created_at: z.string().optional() });
const metrics = z.object({
  check_ins: count.optional(), check_outs: count.optional(), available_rooms: count.optional(),
  occupied_rooms: count.optional(), reserved_rooms: count.optional(), cleaning_rooms: count.optional(),
  total_guests: count.optional(), billed: decimal.optional(), collected: decimal.optional(),
});
const overview = z.object({
  date: day, metrics: metrics.optional(), reservations: z.array(reservation).optional(),
  tasks: z.array(task).optional(), orders: z.array(order).optional(), notifications: z.array(notification).optional(),
});
const pageParts = { count, previous: z.string().nullable(), next: z.string().nullable() };
const notificationPage = z.object({ ...pageParts, results: z.array(notification) });
const repairPage = z.object({ ...pageParts, results: z.array(z.object({ id: identifier, room: identifier, room_number: z.union([z.string(), z.number()]).optional(), description: z.string(), status, blocking: z.boolean() })) });
const invoicePage = z.object({ ...pageParts, results: z.array(z.object({ id: identifier, total: decimal, balance: decimal, closed_at: z.string().nullable() })) });

export type Overview = z.infer<typeof overview>;
export type Metrics = z.infer<typeof metrics>;
export type ReservationSummary = z.infer<typeof reservation>;
export type TaskSummary = z.infer<typeof task>;
export type OrderSummary = z.infer<typeof order>;
export type StaffNotification = z.infer<typeof notification>;
export const decodeOverview = (input: unknown) => overview.parse(input);
export const decodeNotifications = (input: unknown) => notificationPage.parse(input);
export const decodeRepairs = (input: unknown) => repairPage.parse(input);
export const decodeInvoices = (input: unknown) => invoicePage.parse(input);

const longDate = new Intl.DateTimeFormat('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
const shortDate = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
const timestamp = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Africa/Nairobi' });

/** A hotel calendar date is not UTC midnight in the browser's timezone. */
export const calendarDate = (isoDay: string, long = false) => (long ? longDate : shortDate).format(new Date(`${isoDay}T12:00:00Z`));
export function propertyTimestamp(iso: string) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? 'Time unavailable' : `${timestamp.format(date)} EAT`;
}

/** Display the server's fixed-point value without financial arithmetic or rounding in JS. */
export function amount(value: string) {
  const [whole, fraction = ''] = value.split('.');
  return `${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${fraction.padEnd(2, '0')}`;
}
export const statusText = (value: string) => value.replace(/_/g, ' ').replace(/^./, (char) => char.toUpperCase());
