import { useId, useRef, useState, type FormEvent } from 'react';
import { send } from '../../../services/api';
import { AssigneePicker } from '../shared/DirectoryFields';
import { RecordPicker } from '../shared/RecordPicker';
import { useMutation } from '../shared/data';
import { kes, type StaffChoice } from '../shared/format';
import { FormActions, FormHeading, Problem } from '../shared/ui';
import { buildOrder, maxOrderQuantity, type ActiveStay, type DraftLine, type MenuItem, type Order, type Service } from './model';

const blankLine = (key: number): DraftLine => ({ key, item: null, quantity: '1' });
const describeStay = (stay: ActiveStay) => `Stay #${stay.id} · ${stay.rooms.map((r) => `Room ${r.number}`).join(', ')}`;
const describeItem = (item: MenuItem) => `${item.name} · ${kes(item.price)}`;

export function OrderForm({ done, cancel }: { done: (s: string) => void; cancel: () => void }) {
  const [mode, setMode] = useState<Service>('dine-in');
  const [stay, setStay] = useState<ActiveStay | null>(null);
  const [roomId, setRoomId] = useState('');
  const [assignee, setAssignee] = useState<StaffChoice | null>(null);
  const [lines, setLines] = useState<DraftLine[]>([blankLine(1)]);
  const nextKey = useRef(2);
  const mutation = useMutation();
  const serviceName = useId();
  const [revision, setRevision] = useState(0);

  const selectStay = (value: ActiveStay | null) => {
    setStay(value); setRoomId(value?.rooms.length === 1 ? String(value.rooms[0].id) : '');
  };
  const update = (key: number, patch: Partial<Omit<DraftLine, 'key'>>) => {
    setLines((prev) => prev.map((line) => line.key === key ? { ...line, ...patch } : line));
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const draft = buildOrder(mode, stay, roomId, assignee?.id, lines);
    if (!draft.ok) return mutation.fail(draft.error);
    void mutation.run(() => send<Order>('orders/', 'POST', draft.body),
      (order) => done(`Order #${order.id} placed · ${kes(order.total)}. No charge is posted until served.`));
  };

  return <form className="panel ops-form" aria-label="New restaurant order" onSubmit={submit} aria-busy={mutation.busy}>
    <FormHeading hint="Build the ticket before sending it to the kitchen. Prices and availability are checked when you place it.">New order</FormHeading>
    <fieldset className="ops-fieldset ops-stack"><legend>Service destination</legend>
      <div className="ops-inline"><label className="ops-check"><input name={serviceName} type="radio" checked={mode === 'dine-in'}
        onChange={() => { setMode('dine-in'); selectStay(null); }} />Dine-in</label>
        <label className="ops-check"><input name={serviceName} type="radio" checked={mode === 'room-service'}
          onChange={() => setMode('room-service')} />Room service</label></div>
      {mode === 'room-service' ? <div className="form-grid"><RecordPicker label="Active stay" path="orders/stays/" value={stay}
        onChange={selectStay} describe={describeStay} noChoice="Choose an active stay" revision={revision}
        empty="No active stays are available on this page." searchLabel="Find active stay by room or stay number" />
        <label className="field"><span>Service room</span><select required value={roomId} disabled={!stay}
          onChange={(e) => setRoomId(e.target.value)}><option value="">{stay ? 'Choose a room on this stay' : 'Choose a stay first'}</option>
          {stay?.rooms.map((r) => <option value={r.id} key={r.id}>Room {r.number}</option>)}</select></label></div> :
        <small className="muted">A dine-in ticket is billed separately, not to a guest stay.</small>}
    </fieldset>
    {lines.map((line, i) => <fieldset key={line.key} className="ops-fieldset ops-stack"><legend>Order line {i + 1}</legend>
      <div className="form-grid"><RecordPicker<MenuItem> label={`Menu item (line ${i + 1})`} path="menu-items/" filters={{ available: true }} revision={revision}
        value={line.item} onChange={(item) => update(line.key, { item })} describe={describeItem} eligible={(item) => item.available}
        noChoice="Choose an available item" empty="No available items on this page." searchLabel={`Search menu for line ${i + 1}`} />
        <label className="field"><span>Quantity (line {i + 1})</span><input type="number" inputMode="numeric" min="1" max={maxOrderQuantity} step="1" required
          value={line.quantity} onChange={(e) => update(line.key, { quantity: e.target.value })} /></label></div>
      {lines.length > 1 && <div><button type="button" className="btn secondary" onClick={() => setLines((v) => v.filter((l) => l.key !== line.key))}>
        Remove line {i + 1}</button></div>}
    </fieldset>)}
    <div><button type="button" className="btn secondary" onClick={() => {
      const line = blankLine(nextKey.current++); setLines((v) => [...v, line]);
    }}>Add another item</button></div>
    <AssigneePicker role="Restaurant Staff" value={assignee} change={setAssignee} />
    <Problem text={mutation.error} focus />
    {mutation.error && <p className="muted">If your connection was interrupted, refresh the ticket list below before placing this order again.</p>}
    {mutation.error && <div><button className="btn secondary" type="button" onClick={() => {
      setRevision((v) => v + 1); selectStay(null); setLines((v) => v.map((line) => ({ ...line, item: null })));
    }}>Reload and reselect menu items and stay</button></div>}
    <FormActions busy={mutation.busy} submit="Place order" cancel={cancel} />
  </form>;
}
