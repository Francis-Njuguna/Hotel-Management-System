import { useState } from 'react';
import { send } from '../../../services/api';
import { useCollection, useMutation, useWorkspace } from '../shared/data';
import { assignedTo, atHotel, kes, statusText } from '../shared/format';
import { ConfirmAction, LoadState, Notice, Problem, Refresh, SearchBox, Status, StatusFilter } from '../shared/ui';
import { OrderForm } from './OrderForm';
import { OrderAssignment } from './OrderAssignment';
import { advanceOrder, orderStates, type Order, type OrderStatus } from './model';

function OrderCard({ order, work, done }: { order: Order; work: boolean; done: (s: string) => void }) {
  const [assigning, setAssigning] = useState(false);
  const mutation = useMutation();
  const next = advanceOrder(order.status);
  const beforePrep = order.status === 'pending' || order.status === 'confirmed';
  const destination = order.reservation ? `Room service · Stay #${order.reservation}` : 'Dine-in';
  const transition = (status: OrderStatus) => {
    void mutation.run(() => send<Order>(`orders/${order.id}/transition/`, 'POST', { status }),
      (saved) => done(`Order #${order.id} ${statusText(saved.status).toLowerCase()}${saved.status === 'served' ? ' and charge posted' : ''}.`));
  };
  return <article className="ops-record" aria-label={`Order ${order.id}`}><div className="ops-row-head"><div>
    <span className="muted">{destination}{order.room ? (order.room_number ? ` · Room ${order.room_number}` : ` · Room ID ${order.room}`) : ''}</span>
    <h3>Order #{order.id}</h3></div><Status value={order.status} /></div>
    <ul className="ops-line-list" aria-label="Ordered items">{order.items.map((line) => <li key={line.id ?? line.menu_item}>
      <strong>{line.quantity} × {line.menu_item_name || `Menu item #${line.menu_item}`}</strong> <span className="muted">· {kes(line.unit_price)} each</span>
    </li>)}</ul>
    <dl><div><dt>Ticket total</dt><dd>{kes(order.total)}</dd></div>
      <div><dt>Assigned to</dt><dd>{assignedTo(order.assignee, order.assignee_name)}</dd></div>
      <div><dt>Placed</dt><dd><time dateTime={order.created_at}>{atHotel(order.created_at)}</time></dd></div></dl>
    {work && beforePrep && assigning && <OrderAssignment id={order.id} hasAssignee={order.assignee !== null} busy={mutation.busy}
      save={(assignee) => { void mutation.run(() => send<Order>(`orders/${order.id}/`, 'PATCH', { assignee }),
        (saved) => done(saved.assignee ? `Order #${saved.id} assigned to ${assignedTo(saved.assignee, saved.assignee_name)}.` : `Order #${saved.id} is now unassigned.`)); }}
      cancel={() => { setAssigning(false); mutation.fail(''); }} />}
    {work && next && !assigning && <div className="actions ops-actions">{next.target === 'served' ? <ConfirmAction label={next.label}
      question={order.reservation ? `Serve this order and post ${kes(order.total)} to stay #${order.reservation}? This does not record a payment.` :
        `Serve this order and post ${kes(order.total)} to its dine-in invoice? This does not record a payment.`}
      confirm="Confirm serve and post" busy={mutation.busy} execute={() => transition('served')} /> :
      <button className="btn primary" type="button" disabled={mutation.busy} onClick={() => transition(next.target)}>
        {mutation.busy ? 'Saving…' : next.label}</button>}
      {beforePrep && <button className="btn secondary" type="button" disabled={mutation.busy} onClick={() => setAssigning(true)}>
        {order.assignee ? 'Change assignment' : 'Assign order'}</button>}
      <ConfirmAction label="Cancel order"
        question={`${beforePrep ? '' : 'Kitchen preparation has already started. '}Cancel order #${order.id} without posting a charge?`}
        confirm="Confirm cancellation" busy={mutation.busy} execute={() => transition('cancelled')} /></div>}
    <Problem text={mutation.error} focus />
  </article>;
}

export function OrderDesk({ work }: { work: boolean }) {
  const [creating, setCreating] = useState(false);
  const [status, setStatus] = useState('');
  const [search, setSearch] = useState('');
  const ws = useWorkspace();
  const list = useCollection<Order>('orders/', { status, search }, ws.revision);
  return <section className="ops-stack" aria-label="Restaurant orders"><div className="ops-section-head"><div><h2>Order tickets</h2>
    <p className="muted">Track kitchen progress. Record service after delivery to post the charge, not a payment.</p></div>
    {work && !creating && <button type="button" className="btn primary" onClick={() => { ws.clearNotice(); setCreating(true); }}>New order</button>}</div>
    <Notice text={ws.notice} />
    {work && creating && <OrderForm cancel={() => setCreating(false)}
      done={(message) => { setCreating(false); ws.changed(message); }} />}
    <div className="panel ops-stack"><div className="toolbar ops-filters"><SearchBox label="Find ticket by number, room or item" value={search} change={setSearch} />
      <StatusFilter label="Order status" value={status}
      change={setStatus} options={orderStates} /><Refresh onClick={list.retry} /></div>
      <LoadState list={list} name="orders" empty={status || search ? 'No orders match these filters.' : 'No order tickets have been placed.'}>
        {(rows) => <div className="ops-records">{rows.map((order) => <OrderCard key={order.id} order={order} work={work} done={ws.changed} />)}</div>}</LoadState>
    </div>
  </section>;
}
