import {
  BedDouble, Bell, BookOpenCheck, Brush, CalendarDays, CarFront, ClipboardList,
  LayoutDashboard, ReceiptText, UserRoundCog, UsersRound, Utensils, Wrench,
  type LucideIcon,
} from 'lucide-react';
import type { SessionUser } from '../services/api';
import { can } from '../services/session';

export type WorkspaceKey = 'overview' | 'reservations' | 'rooms' | 'guests' | 'housekeeping'
  | 'restaurant' | 'parking' | 'billing' | 'staff' | 'notifications';

export type WorkspaceLink = {
  key: WorkspaceKey;
  path: string;
  label: string;
  description: string;
  icon: LucideIcon;
  group: 'Workspace' | 'Front desk' | 'Operations' | 'Office';
  anyOf: string[];
};

const entries: WorkspaceLink[] = [
  { key: 'overview', path: '/', label: 'Overview', description: 'Your daily shift briefing', icon: LayoutDashboard, group: 'Workspace', anyOf: ['dashboard.view'] },
  { key: 'reservations', path: '/reservations', label: 'Reservations', description: 'Bookings, arrivals and departures', icon: CalendarDays, group: 'Front desk', anyOf: ['reservations.view'] },
  { key: 'rooms', path: '/rooms', label: 'Rooms', description: 'Inventory and room availability', icon: BedDouble, group: 'Front desk', anyOf: ['rooms.view'] },
  { key: 'guests', path: '/guests', label: 'Guests', description: 'Guest profiles and stay history', icon: UsersRound, group: 'Front desk', anyOf: ['guests.view'] },
  { key: 'housekeeping', path: '/housekeeping', label: 'Housekeeping & repairs', description: 'Cleaning tasks and maintenance', icon: Brush, group: 'Operations', anyOf: ['housekeeping.view', 'maintenance.view'] },
  { key: 'restaurant', path: '/restaurant', label: 'Restaurant', description: 'Menu and service orders', icon: Utensils, group: 'Operations', anyOf: ['restaurant.view'] },
  { key: 'parking', path: '/parking', label: 'Parking', description: 'Vehicles and space allocations', icon: CarFront, group: 'Operations', anyOf: ['parking.view'] },
  { key: 'billing', path: '/billing', label: 'Billing', description: 'Invoices and received tender', icon: ReceiptText, group: 'Office', anyOf: ['billing.view'] },
  { key: 'staff', path: '/staff', label: 'Staff & activity', description: 'Staff accounts and activity history', icon: UserRoundCog, group: 'Office', anyOf: ['staff.manage', 'audit.view'] },
  { key: 'notifications', path: '/notifications', label: 'Notifications', description: 'Messages addressed to you', icon: Bell, group: 'Workspace', anyOf: ['dashboard.view'] },
];

export const navigationGroups = ['Workspace', 'Front desk', 'Operations', 'Office'] as const;

export function workspaceLink(key: WorkspaceKey, user: SessionUser | null): WorkspaceLink {
  const item = entries.find((entry) => entry.key === key)!;
  if (key === 'housekeeping' && user) {
    if (!can(user, 'housekeeping.view')) return { ...item, label: 'Maintenance', description: 'Your assigned work orders', icon: Wrench };
    if (!can(user, 'maintenance.view')) return { ...item, label: 'Housekeeping', description: 'Your assigned cleaning tasks' };
  }
  if (key === 'staff' && user && !can(user, 'staff.manage')) {
    return { ...item, label: 'Activity history', description: 'Review operational events', icon: ClipboardList };
  }
  if (key === 'billing' && user && !can(user, 'billing.manage')) {
    return { ...item, description: 'Look up guest folios', icon: BookOpenCheck };
  }
  return item;
}

export function canOpen(user: SessionUser | null, key: WorkspaceKey) {
  return Boolean(user && workspaceLink(key, user).anyOf.some((capability) => can(user, capability)));
}

export function linksFor(user: SessionUser | null) {
  return entries.filter(({ key }) => canOpen(user, key)).map(({ key }) => workspaceLink(key, user));
}

export function initials(name: string) {
  const parts = name.trim().split(/\s+/u).filter(Boolean);
  return [parts[0], ...(parts.length > 1 ? [parts[parts.length - 1]] : [])]
    .map((part) => Array.from(part ?? '')[0] ?? '').join('').toLocaleUpperCase() || 'A';
}

/** A single opaque link segment, never an origin, alternate path or decoded staff identity. */
export function isVerificationLink(pathname: string) {
  return /^\/verify-email\/[^/?#\\\s]+\/?$/.test(pathname) && !/%(?:00|2f|5c)/i.test(pathname);
}

/** Only known, same-origin workspace paths (including signed-in email verification) may be resumed. */
export function resumePath(value: unknown): string {
  if (typeof value !== 'string' || !value.startsWith('/') || /^\/[/\\]/.test(value)) return '/';
  try {
    const base = 'https://workspace.invalid';
    const target = new URL(value, base);
    if (target.origin !== base) return '/';
    const pathname = target.pathname.replace(/\/$/, '') || '/';
    if (isVerificationLink(pathname)) return pathname;
    if (!entries.some(({ path }) => path === pathname) && pathname !== '/verify-email') return '/';
    return pathname + target.search + target.hash;
  } catch {
    return '/';
  }
}
