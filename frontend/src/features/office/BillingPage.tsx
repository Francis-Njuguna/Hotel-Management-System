import { useState, type FormEvent } from 'react';
import { can } from '../../services/api';
import { useSession } from '../../services/session';
import { decimalString, methodLabels, money, nairobiTime, readInvoice, readInvoices, readPayments, type Invoice, type Payment } from './model';
import { Pagination, ReadResult, SectionHeading, useRead } from './ui';
import { InvoiceEntry, type EntryKind } from './InvoiceEntry';
import { Receipt } from './Receipt';

function NumberLookup({ booking = false, initial = '', onLookup }: { booking?: boolean; initial?: string; onLookup: (id: number) => void }) {
  const [lookup, setLookup] = useState(initial);
  const [error, setError] = useState('');
  function find(event: FormEvent) {
    event.preventDefault();
    const id = Number(lookup.trim());
    if (!/^[1-9]\d*$/.test(lookup.trim()) || !Number.isSafeInteger(id)) {
      setError(`Enter a valid ${booking ? 'booking' : 'invoice'} number.`);
      return;
    }
    onLookup(id);
  }
  return <form className="actions" onSubmit={find}>
    <label className="field">{booking ? 'Booking number' : 'Invoice number'}
      <input inputMode="numeric" value={lookup} placeholder={booking ? 'Booking ID' : 'Invoice ID'} required
        onChange={e => { setLookup(e.target.value); setError(''); }} />
    </label>
    <button type="submit" className="btn secondary">{booking ? 'Find folio' : 'Find invoice'}</button>
    {error && <p role="alert" className="error">{error}</p>}
  </form>;
}

function InvoiceList({ page, onPage, onOpen, booking }: {
  page: number; onPage: (n: number) => void; onOpen: (id: number) => void; booking: number | null;
}) {
  const query = new URLSearchParams({ page: String(page) });
  if (booking !== null) query.set('reservation', String(booking));
  const request = useRead(`invoices/?${query}`, readInvoices);
  return <section className="panel" aria-label="Invoice register">
    <div className="toolbar">
      <div><h2>{booking !== null ? `Folios for booking #${booking}` : 'Invoice register'}</h2>
        <p className="muted">Charges, receipts and open balances in KES.</p></div>
      {booking === null && <NumberLookup onLookup={onOpen} />}
    </div>
    <ReadResult request={request} label="invoices">{data => booking !== null && data.results.some(row => row.reservation !== booking)
      ? <p role="alert" className="error">The returned folios do not match this booking. No records are displayed.</p> : <>
      {data.results.length ? <div className="table-wrap"><table aria-label="Invoices">
        <thead><tr><th scope="col">Invoice</th><th scope="col">Booking</th><th scope="col">Status</th>
          <th scope="col">Charged</th><th scope="col">Received</th><th scope="col">Balance</th></tr></thead>
        <tbody>{data.results.map(invoice => <tr key={invoice.id}>
          <th scope="row"><button type="button" className="btn secondary" onClick={() => onOpen(invoice.id)}>
            Invoice #{invoice.id}</button></th>
          <td>{invoice.reservation === null ? 'Standalone' : `#${invoice.reservation}`}</td>
          <td><span className="badge">{invoice.closed_at ? 'Closed' : 'Open'}</span></td>
          <td>{money(invoice.total)}</td><td>{money(invoice.paid)}</td><td>{money(invoice.balance)}</td>
        </tr>)}</tbody>
      </table></div> : <p className="empty">{booking !== null ? 'No folio on record for this booking.' : 'No invoices to display.'}</p>}
      <Pagination label="Invoices" data={data} page={page} onPage={onPage} />
    </>}</ReadResult>
  </section>;
}

function InvoiceLines({ invoice }: { invoice: Invoice }) {
  const withTotal = invoice.items.some(item => item.line_total !== undefined);
  const withSource = invoice.items.some(item => item.source_key);
  return <section className="panel" aria-label="Invoice lines">
    <h3>Charge details</h3>
    {invoice.items.length ? <div className="table-wrap"><table aria-label="Charge details">
      <thead><tr><th scope="col">Description</th><th scope="col">Quantity</th><th scope="col">Unit price</th>
        {withTotal && <th scope="col">Line total</th>}{withSource && <th scope="col">Posting reference</th>}</tr></thead>
      <tbody>{invoice.items.map(item => <tr key={item.id}>
        <th scope="row">{item.description}</th><td>{item.quantity}</td><td>{money(item.unit_price)}</td>
        {withTotal && <td>{item.line_total !== undefined ? money(item.line_total) : 'Not supplied'}</td>}
        {withSource && <td>{item.source_key || 'Not supplied'}</td>}
      </tr>)}</tbody>
    </table></div> : <p className="empty">No charges have been posted to this invoice.</p>}
  </section>;
}

function PaymentRows({ payments, onReceipt }: { payments: Payment[]; onReceipt: (id: number) => void }) {
  return payments.length ? <div className="table-wrap"><table aria-label="Payments received">
      <thead><tr><th scope="col">Receipt</th><th scope="col">Received (Nairobi time)</th><th scope="col">Method</th>
        <th scope="col">Reference</th><th scope="col">Amount</th></tr></thead>
      <tbody>{payments.map(payment => <tr key={payment.id}>
        <th scope="row"><button type="button" className="btn secondary" onClick={() => onReceipt(payment.id)}>
          {payment.receipt_number}</button></th>
        <td><time dateTime={payment.created_at}>{nairobiTime(payment.created_at)}</time></td>
        <td>{methodLabels[payment.method]}</td><td>{payment.reference}</td><td>{money(payment.amount)}</td>
      </tr>)}</tbody>
    </table></div> : <p className="empty">No received payments on record for this invoice.</p>;
}

const paymentsPerPage = 25;
function PaymentPages({ invoiceId, onReceipt }: { invoiceId: number; onReceipt: (id: number) => void }) {
  const [page, setPage] = useState(1);
  const request = useRead(`invoices/${invoiceId}/payments/?page=${page}&page_size=${paymentsPerPage}`, readPayments);
  return <ReadResult request={request} label="invoice payments">{data => data.results.every(row => row.invoice === invoiceId) ? <>
    <PaymentRows payments={data.results} onReceipt={onReceipt} />
    <Pagination label="Payments" data={data} page={page} onPage={setPage} />
  </> : <p className="error" role="alert">The payment records do not match this invoice.</p>}</ReadResult>;
}

function InvoicePayments({ invoice, onReceipt }: { invoice: Invoice; onReceipt: (id: number) => void }) {
  return <section className="panel" aria-label="Payments received">
    <h3>Payments received</h3>
    {/* Reuse the server's consistent detail snapshot when it fits on one page. */}
    {invoice.payments.length <= paymentsPerPage ? <PaymentRows payments={invoice.payments} onReceipt={onReceipt} />
      : <PaymentPages invoiceId={invoice.id} onReceipt={onReceipt} />}
  </section>;
}

function InvoiceDetail({ id, booking, canPost, onBack, onReceipt }: {
  id: number; booking: number | null; canPost: boolean; onBack: () => void; onReceipt: (id: number, justRecorded?: boolean) => void;
}) {
  const request = useRead(`invoices/${id}/`, readInvoice);
  const [entry, setEntry] = useState<EntryKind | null>(null);
  const [notice, setNotice] = useState('');
  function finishEntry(message: string) {
    setEntry(null);
    setNotice(message);
    request.retry();
  }
  return <>
    <div className="toolbar"><SectionHeading>Invoice #{id}</SectionHeading>
      {!entry && <button type="button" className="btn secondary" onClick={onBack}>{canPost ? 'Back to invoices' : 'Back to folio lookup'}</button>}
    </div>
    {notice && <p className="notice" role="status">{notice}</p>}
    <ReadResult request={request} label="invoice details">{invoice => {
        if (invoice.id !== id || (booking !== null && invoice.reservation !== booking)) {
          return <p className="error" role="alert">The requested invoice could not be identified.</p>;
        }
        const open = invoice.closed_at === null;
        const balance = decimalString(invoice.balance);
        const payable = balance !== null && balance !== '0.00';
        const startEntry = (kind: EntryKind) => { setNotice(''); setEntry(kind); };
        return <>
          <section className="panel" aria-label="Invoice summary">
            <p><span className="badge">{open ? 'Open' : 'Closed'}</span>{' · '}
              {invoice.reservation === null ? 'Standalone invoice' : `Booking #${invoice.reservation}`}{' · '}
              Opened <time dateTime={invoice.created_at}>{nairobiTime(invoice.created_at)}</time> (Nairobi)</p>
            <dl className="card-grid" aria-label="Invoice totals">
              <div><dt className="muted">Charged</dt><dd>{money(invoice.total)}</dd></div>
              <div><dt className="muted">Received</dt><dd>{money(invoice.paid)}</dd></div>
              <div><dt className="muted">Balance due</dt><dd><strong>{money(invoice.balance)}</strong></dd></div>
            </dl>
            {canPost && open && !entry && <div className="actions">
              <button type="button" className="btn secondary" onClick={() => startEntry('charge')}>Add charge</button>
              {payable && <button type="button" className="btn primary" onClick={() => startEntry('payment')}>Record payment</button>}
            </div>}
            {canPost && !open && <p className="muted">This invoice is closed to new entries.</p>}
          </section>
          {canPost && open && entry ? <InvoiceEntry key={entry} kind={entry} invoice={invoice}
            onCancel={() => finishEntry('')} onCharge={() => finishEntry('Charge recorded.')}
            onPayment={payment => onReceipt(payment.id, true)} /> : <>
            <InvoiceLines invoice={invoice} />
            <InvoicePayments invoice={invoice} onReceipt={onReceipt} />
          </>}
        </>;
    }}</ReadResult>
  </>;
}

type BillingView = { kind: 'list' } | { kind: 'invoice'; id: number } |
  { kind: 'receipt'; id: number; invoice: number; justRecorded: boolean };

function BillingWorkspace({ canPost }: { canPost: boolean }) {
  const [view, setView] = useState<BillingView>({ kind: 'list' });
  const [page, setPage] = useState(1);
  const [booking, setBooking] = useState<number | null>(null);
  return <>
    {!canPost && <p className="notice">Read-only access. You can look up invoices and receipts, but cannot post charges or payments.</p>}
    {!canPost && view.kind === 'list' && <section className="panel" aria-label="Booking folio lookup">
      <h2>Look up a booking folio</h2><p className="muted">Use the booking number from the reservation you are handling.</p>
      <NumberLookup booking initial={booking === null ? '' : String(booking)} onLookup={id => { setPage(1); setBooking(id); }} />
    </section>}
    {view.kind === 'list' && (canPost || booking !== null) && <InvoiceList page={page} booking={booking} onPage={setPage}
      onOpen={id => setView({ kind: 'invoice', id })} />}
    {view.kind === 'invoice' && <InvoiceDetail key={view.id} id={view.id} booking={booking} canPost={canPost}
      onBack={() => setView({ kind: 'list' })}
      onReceipt={(id, justRecorded = false) => setView({ kind: 'receipt', invoice: view.id, id, justRecorded })} />}
    {view.kind === 'receipt' && <Receipt id={view.id} invoice={view.invoice} justRecorded={view.justRecorded}
      onBack={() => setView({ kind: 'invoice', id: view.invoice })} />}
  </>;
}

export function BillingPage() {
  const { user, loading } = useSession();
  return <section className="page office-page" aria-labelledby="office-billing-title">
    <header className="page-header"><div><p className="eyebrow">Finance</p>
      <h1 id="office-billing-title">Billing</h1><p className="muted">Review posted charges and trace each receipt to a received payment.</p>
    </div></header>
    {loading ? <p role="status">Checking access…</p> : user && can(user, 'billing.view')
      ? <BillingWorkspace key={`${user.id}:${can(user, 'billing.manage')}`} canPost={can(user, 'billing.manage')} />
      : <p className="notice" role="status">You do not have access to billing records.</p>}
  </section>;
}
