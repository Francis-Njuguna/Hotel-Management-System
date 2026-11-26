import { ArrowDownLeft, ArrowUpRight, Banknote, BedDouble, Brush, CheckCheck, ClipboardList, ConciergeBell, DoorOpen, KeyRound, LogIn, LogOut, ReceiptText, UsersRound, type LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { SessionUser } from '../../services/api';
import { can } from '../../services/session';
import { amount, type Metrics, type Overview } from './model';
import { Board } from './Panel';

export type Indicator = { key: string; label: string; caption: string; icon: LucideIcon; tone: string; value: string; path: string; money?: boolean };
const facts: Array<Omit<Indicator, 'value' | 'key'> & { key: keyof Metrics; cap: string }> = [
  { key: 'check_ins', label: 'Check-ins', caption: 'Scheduled today', icon: LogIn, tone: 'blue', path: '/reservations', cap: 'reservations.view' },
  { key: 'check_outs', label: 'Check-outs', caption: 'Scheduled today', icon: LogOut, tone: 'violet', path: '/reservations', cap: 'reservations.view' },
  { key: 'available_rooms', label: 'Available rooms', caption: 'Free on tonight’s calendar', icon: KeyRound, tone: 'teal', path: '/rooms', cap: 'rooms.view' },
  { key: 'occupied_rooms', label: 'Occupied rooms', caption: 'Currently in house', icon: BedDouble, tone: 'amber', path: '/rooms', cap: 'rooms.view' },
  { key: 'billed', label: 'Billed today', caption: 'Charges posted', icon: ReceiptText, tone: 'blue', path: '/billing', cap: 'billing.manage', money: true },
  { key: 'collected', label: 'Collected today', caption: 'Tender received', icon: Banknote, tone: 'teal', path: '/billing', cap: 'billing.manage', money: true },
  { key: 'reserved_rooms', label: 'Reserved rooms', caption: 'On the room calendar', icon: DoorOpen, tone: 'blue', path: '/rooms', cap: 'rooms.view' },
  { key: 'cleaning_rooms', label: 'Rooms to clean', caption: 'Marked dirty', icon: Brush, tone: 'violet', path: '/rooms', cap: 'rooms.view' },
  { key: 'total_guests', label: 'Guest profiles', caption: 'Registered guests', icon: UsersRound, tone: 'teal', path: '/guests', cap: 'guests.view' },
];
const integer = new Intl.NumberFormat('en-GB');

export function indicators(data: Overview, user: SessionUser): Indicator[] {
  const visible = facts.flatMap((item) => {
    const value = data.metrics?.[item.key];
    if (value === undefined || !can(user, item.cap)) return [];
    return [{ ...item, value: typeof value === 'string' ? amount(value) : integer.format(value) }];
  });
  if (visible.length) return visible;
  // Departmental feeds are bounded. These are counts in the preview, NOT property-wide totals.
  const department: Indicator[] = [];
  if (data.tasks && can(user, 'housekeeping.view')) department.push(
    { key: 'task-list', label: 'Cleaning tasks', caption: 'In this briefing', value: integer.format(data.tasks.length), path: '/housekeeping', icon: ClipboardList, tone: 'blue' },
    { key: 'task-progress', label: 'In progress', caption: 'In the cleaning queue below', value: integer.format(data.tasks.filter((t) => t.status === 'in_progress').length), path: '/housekeeping', icon: Brush, tone: 'teal' },
  );
  if (data.orders && can(user, 'restaurant.view')) department.push(
    { key: 'order-list', label: 'Service orders', caption: 'In this briefing', value: integer.format(data.orders.length), path: '/restaurant', icon: ConciergeBell, tone: 'blue' },
    { key: 'orders-ready', label: 'Ready to serve', caption: 'In the service queue below', value: integer.format(data.orders.filter((o) => o.status === 'ready').length), path: '/restaurant', icon: CheckCheck, tone: 'amber' },
  );
  return department;
}

export function Snapshot({ items }: { items: Indicator[] }) {
  if (!items.length) return null;
  return <section className="snapshot" aria-labelledby="snapshot-title"><div className="section-line"><h2 id="snapshot-title">Shift snapshot</h2><span className="section-rule" /></div>
    <div className="metric-grid" data-count={items.length}>{items.map(({ key, label, value, caption, path, icon: Icon, tone, money }) => <Link key={key} to={path} className={`metric-tile tone-${tone}`}>
      <div className="metric-heading"><span className="metric-icon"><Icon size={19} strokeWidth={1.9} aria-hidden="true" /></span><ArrowUpRight size={15} className="metric-arrow" aria-hidden="true" /></div>
      <div className="metric-label">{label}</div><div className={`metric-value${money ? ' currency-value' : ''}`}>{money && <small>KES </small>}{value}</div>
      <div className="metric-caption">{caption}</div>
    </Link>)}</div></section>;
}

export function OtherIndicators({ items }: { items: Indicator[] }) {
  const property = items.filter((item) => !item.money);
  const ledger = items.filter((item) => item.money);
  return <>{property.length > 0 && <Board title="Property register" kicker="Inventory" icon={BedDouble}>
    <ul className="indicator-list">{property.map(({ key, icon: Icon, value, label, path }) => <li key={key}><Link to={path}><Icon size={17} aria-hidden="true" />
      <span>{label}</span><strong>{value}</strong><ArrowUpRight size={14} aria-hidden="true" /></Link></li>)}</ul>
  </Board>}{ledger.length > 0 && <Board title="Posting summary" kicker="Finance today" icon={ReceiptText} link="/billing" linkLabel="View finance workspace">
    <div className="ledger-pair">{ledger.map(({ key, label, value, caption }) => <div key={key} className={`ledger-item ${key}`}>
      {key === 'collected' ? <ArrowDownLeft size={17} aria-hidden="true" /> : <ArrowUpRight size={17} aria-hidden="true" />}<div><span>{label}</span><strong>KES {value}</strong><small>{caption}</small></div></div>)}</div>
  </Board>}</>;
}
