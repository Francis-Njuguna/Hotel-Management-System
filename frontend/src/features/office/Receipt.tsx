import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { methodLabels, money, nairobiTime, positiveAmount, readPayment, type Payment } from './model';
import { ReadResult, SectionHeading, useRead } from './ui';
import './receipt.css';

function ReceiptDocument({ payment }: { payment: Payment }) {
  return <article className="panel" aria-label="Individual payment receipt">
    <p className="eyebrow">Hotel A · Payment receipt</p>
    <h3>Receipt {payment.receipt_number}</h3>
    <dl>
      <div><dt>Amount received</dt><dd><strong>{money(payment.amount)}</strong></dd></div>
      <div><dt>Invoice</dt><dd>#{payment.invoice}</dd></div>
      <div><dt>Payment method</dt><dd>{methodLabels[payment.method]}</dd></div>
      <div><dt>Payment reference</dt><dd>{payment.reference}</dd></div>
      <div><dt>Recorded (Nairobi time)</dt><dd><time dateTime={payment.created_at}>{nairobiTime(payment.created_at)}</time></dd></div>
      <div><dt>Received by</dt><dd>Staff #{payment.received_by}</dd></div>
    </dl>
    <p className="muted">This receipt acknowledges only the payment shown.</p>
  </article>;
}

function PrintableReceipt({ payment }: { payment: Payment }) {
  useEffect(() => {
    document.body.classList.add('office-receipt-open');
    return () => document.body.classList.remove('office-receipt-open');
  }, []);
  return <>
    <ReceiptDocument payment={payment} />
    <div className="actions"><button type="button" className="btn primary" onClick={() => window.print()}>Print receipt</button></div>
    {createPortal(<div aria-hidden="true" className="office-print-copy"><ReceiptDocument payment={payment} /></div>, document.body)}
  </>;
}

export function Receipt({ id, invoice, justRecorded, onBack }: {
  id: number; invoice: number; justRecorded: boolean; onBack: () => void;
}) {
  const request = useRead(`payments/${id}/`, readPayment);
  return <>
    <div className="actions"><button type="button" className="btn secondary" onClick={onBack}>Back to invoice #{invoice}</button></div>
    <SectionHeading>Payment receipt</SectionHeading>
    {justRecorded && <p className="notice" role="status">Payment on record. This receipt is for the individual tender, not the invoice total.</p>}
    <ReadResult request={request} label="payment receipt">{payment => {
      if (payment.id !== id || payment.invoice !== invoice || !payment.receipt_number.trim() ||
        !payment.reference.trim() || !positiveAmount(payment.amount)) {
        return <p className="error" role="alert">The server did not return a complete matching payment. No printable receipt is available.</p>;
      }
      return <PrintableReceipt payment={payment} />;
    }}</ReadResult>
  </>;
}
