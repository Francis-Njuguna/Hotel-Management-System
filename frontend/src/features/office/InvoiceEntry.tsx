import { useState, type FormEvent } from 'react';
import { send } from '../../services/api';
import { decimalString, exceeds, methodLabels, money, positiveAmount, readPayment, readPostedLine, type Invoice, type Payment, type PaymentMethod } from './model';
import { SectionHeading, useCommand } from './ui';

export type EntryKind = 'charge' | 'payment';
type ReviewedEntry =
  | { kind: 'charge'; body: { description: string; quantity: number; unit_price: string; reference: string } }
  | { kind: 'payment'; body: { amount: string; method: PaymentMethod; reference: string } };

export function InvoiceEntry({ kind, invoice, onCharge, onPayment, onCancel }: {
  kind: EntryKind; invoice: Invoice; onCharge: () => void; onPayment: (payment: Payment) => void; onCancel: () => void;
}) {
  const [description, setDescription] = useState('');
  const [quantity, setQuantity] = useState('1');
  const [amount, setAmount] = useState('');
  const [method, setMethod] = useState<PaymentMethod | ''>('');
  const [reference, setReference] = useState('');
  const [verified, setVerified] = useState(false);
  const [error, setError] = useState('');
  const [reviewed, setReviewed] = useState<ReviewedEntry | null>(null);
  const command = useCommand();

  function review(event: FormEvent) {
    event.preventDefault();
    setError('');
    const value = kind === 'payment' ? positiveAmount(amount) : decimalString(amount);
    const ref = reference.trim();
    if (!value || value.length > 13) {
      setError(`Enter a ${kind === 'payment' ? 'positive amount' : 'non-negative unit price'} in KES with at most ten integer digits and two decimal places.`); return;
    }
    if (!ref) { setError('Enter the reference from the source record.'); return; }
    if (kind === 'charge') {
      const count = Number(quantity);
      if (!description.trim()) { setError('Describe the service or item supplied.'); return; }
      if (!/^\d+$/.test(quantity) || !Number.isSafeInteger(count) || count < 1 || count > 2147483647) {
        setError('Quantity must be a positive whole number.'); return;
      }
      setReviewed({ kind, body: { description: description.trim(), quantity: count, unit_price: value, reference: ref } });
    } else {
      const balance = decimalString(invoice.balance);
      if (balance === null || exceeds(value, balance)) { setError('Amount received cannot exceed the recorded balance.'); return; }
      if (!method || !Object.hasOwn(methodLabels, method)) { setError('Select the method actually received.'); return; }
      setReviewed({ kind, body: { amount: value, method, reference: ref } });
    }
    setVerified(false);
  }

  function post(event: FormEvent) {
    event.preventDefault();
    if (!reviewed || command.pending) return;
    if (reviewed.kind === 'charge') {
      void command.run(() => send(`invoices/${invoice.id}/charges/`, 'POST', reviewed.body).then(readPostedLine), line => {
        if (line.invoice !== invoice.id || line.description !== reviewed.body.description || line.quantity !== reviewed.body.quantity ||
          decimalString(line.unit_price) !== reviewed.body.unit_price) throw new Error('No matching charge was returned. Check the invoice.');
        onCharge();
      });
    } else if (verified) {
      // The same, frozen payload is used on every retry, including after a lost response.
      void command.run(() => send(`invoices/${invoice.id}/payments/`, 'POST', reviewed.body).then(readPayment), payment => {
        if (payment.invoice !== invoice.id || !payment.receipt_number.trim() || payment.method !== reviewed.body.method ||
          decimalString(payment.amount) !== reviewed.body.amount || payment.reference !== reviewed.body.reference) {
          throw new Error('No matching receipt was returned. Check the invoice before making another entry.');
        }
        onPayment(payment);
      });
    }
  }

  if (reviewed) {
    const uncertain = !!command.failure && ![400, 403, 404, 409].includes(command.failure.status ?? 0);
    const conflict = command.failure?.status === 409;
    return <form key="review" className="panel" onSubmit={post} aria-label={`Review ${kind}`}>
      <SectionHeading>Review {kind}</SectionHeading>
      <p className="muted">This entry applies to invoice #{invoice.id}.</p>
      <dl>
        {reviewed.kind === 'charge' ? <>
          <div><dt>Description</dt><dd>{reviewed.body.description}</dd></div>
          <div><dt>Quantity</dt><dd>{reviewed.body.quantity}</dd></div>
          <div><dt>Unit price</dt><dd>{money(reviewed.body.unit_price)}</dd></div>
        </> : <>
          <div><dt>Amount received</dt><dd><strong>{money(reviewed.body.amount)}</strong></dd></div>
          <div><dt>Method</dt><dd>{methodLabels[reviewed.body.method]}</dd></div>
        </>}
        <div><dt>Reference</dt><dd>{reviewed.body.reference}</dd></div>
      </dl>
      {reviewed.kind === 'payment' && <label>
        <input type="checkbox" checked={verified} required disabled={command.pending}
          onChange={e => setVerified(e.target.checked)} />{' '}
        {reviewed.body.method === 'cash' ? 'I have received and counted this cash and checked the till reference.'
          : 'I have verified this received amount and reference against the external transaction record.'}
      </label>}
      {command.failure && <div className="error" role="alert">
        <p>{command.failure.message}</p>
        <p>{uncertain ? 'The result is not confirmed. Check the invoice or retry this exact entry. Do not use a new reference.'
          : conflict ? 'This entry conflicts with the current ledger. Check the invoice before starting another entry; do not substitute a new reference.'
          : 'Check the details against the invoice and the original record before retrying.'}</p>
      </div>}
      <div className="actions">
        <button type="submit" className="btn primary" disabled={command.pending || (kind === 'payment' && !verified)}>
          {command.pending ? 'Recording…' : command.failure ? `Retry same ${kind}` : `Confirm ${kind}`}
        </button>
        {!uncertain && !conflict && <button type="button" className="btn secondary" disabled={command.pending} onClick={() => {
          command.clearError(); setReviewed(null); setVerified(false);
        }}>Edit entry</button>}
        <button type="button" className="btn secondary" disabled={command.pending} onClick={onCancel}>
          {command.failure ? 'Check invoice' : 'Cancel'}
        </button>
      </div>
    </form>;
  }

  return <form key="entry" className="panel" onSubmit={review} aria-label={kind === 'charge' ? 'Add charge' : 'Record received payment'}>
    <SectionHeading>{kind === 'charge' ? 'Add a charge' : 'Record a received payment'}</SectionHeading>
    <p className="muted">{kind === 'charge'
      ? 'Enter an item or service already supplied. Use its original source reference to avoid a duplicate charge.'
      : 'Record cash already in hand or a payment confirmed by the bank, card or mobile-money provider. This does not move funds.'}</p>
    <div className="form-grid">
      {kind === 'charge' ? <>
        <label className="field">Description<input required maxLength={2000} value={description} onChange={e => setDescription(e.target.value)} /></label>
        <label className="field">Quantity<input required type="number" step="1" min="1" max="2147483647" value={quantity}
          onChange={e => setQuantity(e.target.value)} /></label>
      </> : <label className="field">Payment method<select required value={method}
        onChange={e => setMethod(e.target.value as PaymentMethod | '')}>
        <option value="">Select received method</option>
        {Object.entries(methodLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select></label>}
      <label className="field">{kind === 'charge' ? 'Unit price (KES)' : 'Amount received (KES)'}
        <input required inputMode="decimal" autoComplete="off" placeholder="0.00" value={amount}
          onChange={e => setAmount(e.target.value)} />
      </label>
      <label className="field">{kind === 'charge' ? 'Source reference' : 'Payment reference'}
        <input required maxLength={128} autoComplete="off" value={reference} onChange={e => setReference(e.target.value)}
          aria-describedby="office-reference-help" />
      </label>
    </div>
    <p id="office-reference-help" className="muted">{kind === 'charge' ? 'Use the service slip or other source document identifier.'
      : 'Use the transaction ID or cash voucher reference. Never enter a card number, PIN or bank account details.'}</p>
    {error && <p className="error" role="alert">{error}</p>}
    <div className="actions">
      <button type="submit" className="btn primary">Review {kind}</button>
      <button type="button" className="btn secondary" onClick={onCancel}>Cancel</button>
    </div>
  </form>;
}
