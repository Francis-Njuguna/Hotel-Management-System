import { z } from 'zod';

const id = z.number().int().positive();
const decimal = z.string().regex(/^\d+(?:\.\d{1,2})?$/);
const timestamp = z.string().refine(value => Number.isFinite(Date.parse(value)));
const invoiceSummary = z.object({
  id, reservation: id.nullable(), created_at: timestamp, closed_at: timestamp.nullable(),
  total: decimal, paid: decimal, balance: decimal,
});
const invoiceLine = z.object({
  id, description: z.string(), quantity: id, unit_price: decimal,
  line_total: decimal.optional(), source_key: z.string().optional(),
});
export type InvoiceSummary = z.infer<typeof invoiceSummary>;

export const methodLabels = {
  cash: 'Cash',
  bank: 'Bank transfer',
  mobile_money: 'Mobile money',
  card: 'Card',
} as const;

export type PaymentMethod = keyof typeof methodLabels;

const payment = z.object({
  id, invoice: id, receipt_number: z.string().min(1), amount: decimal,
  method: z.enum(['cash', 'bank', 'mobile_money', 'card']), reference: z.string().min(1), received_by: id, created_at: timestamp,
});
const invoice = invoiceSummary.extend({ items: z.array(invoiceLine), payments: z.array(payment) })
  .refine(record => record.payments.every(tender => tender.invoice === record.id));
export type Payment = z.infer<typeof payment>;
export type Invoice = z.infer<typeof invoice>;

/** Fixed-point throughout: never pass KES through a floating point number. */
export function decimalString(raw: string): string | null {
  const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(raw.trim());
  if (!match) return null;
  return `${match[1].replace(/^0+(?=\d)/, '')}.${(match[2] ?? '').padEnd(2, '0')}`;
}

export function positiveAmount(raw: string): string | null {
  const value = decimalString(raw);
  // Decimal(12,2): at most ten integer digits, a point and two decimals.
  return value && value !== '0.00' && value.length <= 13 ? value : null;
}

export function money(raw: string): string {
  const value = decimalString(raw);
  if (value === null) return 'Amount unavailable';
  const [whole, fraction] = value.split('.');
  return `KES ${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${fraction}`;
}

/** Both operands are canonical, non-negative decimal strings with a scale of 2. */
export function exceeds(amount: string, balance: string): boolean {
  return amount.length > balance.length || (amount.length === balance.length && amount > balance);
}

const localTime = new Intl.DateTimeFormat('en-KE', {
  timeZone: 'Africa/Nairobi', day: 'numeric', month: 'short', year: 'numeric',
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
});

export function nairobiTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? 'Time unavailable' : localTime.format(date);
}

export const roles = [
  'Super Administrator', 'Hotel Manager', 'Receptionist', 'Housekeeping Staff',
  'Restaurant Staff', 'Accountant', 'Maintenance Staff',
] as const;

const staffMember = z.object({
  id, username: z.string().min(1), first_name: z.string(), last_name: z.string(), email: z.string(),
  department: z.string(), role: z.string(), is_active: z.boolean(),
});
const auditEvent = z.object({
  id, actor: id.nullable(), actor_name: z.string().nullish(), verb: z.string(), entity: z.string(),
  object_id: z.union([id, z.string().regex(/^\d+$/)]), summary: z.string(), created_at: timestamp,
});
export type StaffMember = z.infer<typeof staffMember>;
export type AuditEvent = z.infer<typeof auditEvent>;

function pageOf<T extends z.ZodType>(row: T) {
  return z.object({ count: z.number().int().nonnegative(), next: z.string().nullable(), previous: z.string().nullable(), results: z.array(row) });
}
function reader<T>(schema: z.ZodType<T>, label: string) {
  return (value: unknown): T => {
    const result = schema.safeParse(value);
    if (!result.success) throw new Error(`The server returned an incomplete ${label}. Refresh before continuing.`);
    return result.data;
  };
}
export const readInvoices = reader(pageOf(invoiceSummary), 'invoice register');
export const readInvoice = reader(invoice, 'invoice');
export const readPostedLine = reader(invoiceLine.extend({ invoice: id }), 'charge record');
export const readPayment = reader(payment, 'payment record');
export const readPayments = reader(pageOf(payment), 'invoice payment page');
export const readStaff = reader(pageOf(staffMember), 'staff directory');
export const readMember = reader(staffMember, 'staff account');
export const readAudit = reader(pageOf(auditEvent), 'activity page');
