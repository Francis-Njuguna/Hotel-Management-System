export interface MenuItem {
  id: number; name: string; category: string; price: string; available: boolean;
  description: string; image: string | null;
}
export interface StayRoom { id: number; number: string }
export interface ActiveStay { id: number; rooms: StayRoom[] }
export const orderStates = ['pending', 'confirmed', 'preparing', 'ready', 'served', 'cancelled'] as const;
export type OrderStatus = (typeof orderStates)[number];
export interface OrderItem {
  id?: number; menu_item: number; menu_item_name?: string; quantity: number; unit_price: string;
}
export interface Order {
  id: number; reservation: number | null; room: number | null; room_number?: string | null;
  assignee: number | null; assignee_name?: string | null; status: OrderStatus; created_at: string;
  items: OrderItem[]; total: string;
}
export interface DraftLine { key: number; item: MenuItem | null; quantity: string }
export const maxOrderQuantity = 2_147_483_647;
export type Service = 'dine-in' | 'room-service';
interface OrderPayload {
  reservation?: number; room?: number; assignee?: number; items: { menu_item: number; quantity: number }[];
}

/** Construct the allowlisted command, never accepting prices, totals, guest identity or workflow status. */
export function buildOrder(mode: Service, stay: ActiveStay | null, roomId: string,
  assigneeId: number | undefined, lines: DraftLine[]): { ok: true; body: OrderPayload } | { ok: false; error: string } {
  const body: OrderPayload = { items: [] };
  if (mode === 'room-service') {
    if (!stay) return { ok: false, error: 'Choose an active stay for room service.' };
    const room = stay.rooms.find((r) => String(r.id) === roomId);
    if (!room) return { ok: false, error: 'Choose a room belonging to the selected stay.' };
    body.reservation = stay.id;
    body.room = room.id;
  }
  if (assigneeId) body.assignee = assigneeId;
  if (!lines.length) return { ok: false, error: 'Add at least one menu item.' };
  const used = new Set<number>();
  for (const [i, line] of lines.entries()) {
    if (!line.item?.available) return { ok: false, error: `Line ${i + 1}: choose an available menu item.` };
    const quantity = Number(line.quantity);
    if (!/^\d+$/.test(line.quantity) || !Number.isSafeInteger(quantity) || quantity < 1 || quantity > maxOrderQuantity) {
      return { ok: false, error: `Line ${i + 1}: enter a whole quantity from 1 to ${maxOrderQuantity.toLocaleString('en-KE')}.` };
    }
    if (used.has(line.item.id)) return { ok: false, error: `Line ${i + 1}: this item is already on the ticket. Change its quantity instead.` };
    used.add(line.item.id);
    body.items.push({ menu_item: line.item.id, quantity });
  }
  return { ok: true, body };
}

export function advanceOrder(status: OrderStatus): { target: OrderStatus; label: string } | null {
  switch (status) {
    case 'pending': return { target: 'confirmed', label: 'Confirm order' };
    case 'confirmed': return { target: 'preparing', label: 'Start preparation' };
    case 'preparing': return { target: 'ready', label: 'Mark ready' };
    case 'ready': return { target: 'served', label: 'Serve & post charge' };
    default: return null;
  }
}

export function sameOriginImage(path: string | null | undefined): string | undefined {
  if (!path) return;
  try {
    const url = new URL(path, window.location.origin);
    if (url.origin === window.location.origin && ['http:', 'https:'].includes(url.protocol)) return url.href;
  } catch { /* No broken or external preview when the API did not supply a valid private URL. */ }
}
