import { describe, expect, it } from 'vitest';
import { buildOrder, advanceOrder, type ActiveStay, type DraftLine, type MenuItem } from './model';
import { nextCleaningWork } from '../housekeeping/model';

// Synthetic values for command-boundary tests only (never imported by a workspace).
const item: MenuItem = { id: 3, name: 'Test dish', category: 'Test', price: '123.40', available: true, description: '', image: null };
const line: DraftLine = { key: 7, item, quantity: '2' };
const stay: ActiveStay = { id: 10, rooms: [{ id: 12, number: 'T1' }, { id: 14, number: 'T2' }] };

describe('kitchen ticket command', () => {
  it('posts only distinct item IDs, quantities, assignment and the booked room', () => {
    expect(buildOrder('room-service', stay, '14', 8, [line, { key: 8, item: { ...item, id: 4 }, quantity: '1' }]))
      .toEqual({ ok: true, body: { reservation: 10, room: 14, assignee: 8, items: [{ menu_item: 3, quantity: 2 }, { menu_item: 4, quantity: 1 }] } });
  });
  it('does not carry stale room-service fields, prices or totals onto a dine-in order', () => {
    expect(buildOrder('dine-in', stay, '14', undefined, [line]))
      .toEqual({ ok: true, body: { items: [{ menu_item: 3, quantity: 2 }] } });
  });
  it('requires an active selection and explicit room membership', () => {
    expect(buildOrder('room-service', null, '14', undefined, [line]).ok).toBe(false);
    expect(buildOrder('room-service', stay, '', undefined, [line]).ok).toBe(false);
    expect(buildOrder('room-service', stay, '99', undefined, [line]).ok).toBe(false);
  });
  it.each(['', '0', '-1', '1.5', '2e1', '9007199254740993'])('rejects invalid quantity %j', (quantity) => {
    expect(buildOrder('dine-in', null, '', undefined, [{ ...line, quantity }]).ok).toBe(false);
  });
  it('rejects an empty ticket, missing, duplicate and withdrawn choices', () => {
    for (const rows of [[], [{ ...line, item: null }], [line, line], [{ ...line, item: { ...item, available: false } }]]) {
      expect(buildOrder('dine-in', null, '', undefined, rows).ok).toBe(false);
    }
  });
});

describe('work queue controls', () => {
  it('does not offer a worker an inspection transition', () => {
    expect(nextCleaningWork('assigned')?.target).toBe('in_progress');
    expect(nextCleaningWork('in_progress')?.target).toBe('completed');
    expect(nextCleaningWork('completed')).toBeNull();
    expect(nextCleaningWork('inspected')).toBeNull();
  });
  it('offers service only from ready and no progress on a terminal ticket', () => {
    expect(advanceOrder('preparing')?.target).toBe('ready');
    expect(advanceOrder('ready')?.target).toBe('served');
    expect(advanceOrder('served')).toBeNull();
    expect(advanceOrder('cancelled')).toBeNull();
  });
});
