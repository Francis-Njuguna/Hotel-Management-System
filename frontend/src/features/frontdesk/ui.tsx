import { Fragment, useEffect, useId, useRef, useState, type ReactNode } from 'react';
import type { Page, SessionUser } from '../../services/api';
import { can, useSession } from '../../services/session';
import { statusLabel, type BookingStatus } from './model';
import type { ReadResult } from './remote';

export { can };

export function Access({ capability, children }: {
  capability: string; children: (user: SessionUser) => ReactNode;
}) {
  const { user, loading, error, refresh } = useSession();
  if (loading) return <p role="status" className="panel">Checking staff access…</p>;
  if (error) return <div className="panel"><ErrorText>{error}</ErrorText>
    <button className="btn secondary" type="button" onClick={() => { void refresh(); }}>Retry session</button></div>;
  if (!user || !can(user, capability)) {
    return <p role="alert" className="error">Your staff account does not have access to this page.</p>;
  }
  return <Fragment key={user.id}>{children(user)}</Fragment>;
}

export function Header({ title, description, children }: {
  title: string; description: string; children?: ReactNode;
}) {
  return <header className="page-header fd-header">
    <div><p className="eyebrow">Front desk</p><h1 tabIndex={-1}>{title}</h1>
      <p className="muted">{description}</p></div>
    {children && <div className="actions">{children}</div>}
  </header>;
}

export function ErrorText({ children }: { children: string }) {
  return children ? <p className="error fd-message" role="alert">{children}</p> : null;
}

export function Success({ children }: { children: string }) {
  return <div role="status" aria-live="polite" aria-atomic="true" className={children ? undefined : 'fd-sr-only'}>
    {children && <p className="notice fd-message">{children}</p>}
  </div>;
}

export function Feedback({ result, label, firstPage }: {
  result: Pick<ReadResult<unknown>, 'loading' | 'error' | 'retry'>; label: string; firstPage?: () => void;
}) {
  if (result.loading) return <p role="status" className="muted">{label}…</p>;
  if (!result.error) return null;
  return <div className="fd-stack"><ErrorText>{result.error}</ErrorText><div className="actions">
    <button className="btn secondary" type="button" onClick={result.retry}>Retry</button>
    {firstPage && <button className="btn secondary" type="button" onClick={firstPage}>Back to first page</button>}
  </div></div>;
}

export function Pager({ label, page, size, data, change }: {
  label: string; page: number; size: number; data: Pick<Page<unknown>, 'count' | 'next' | 'previous'>;
  change: (page: number) => void;
}) {
  return <nav aria-label={`${label} pages`} className="fd-pager">
    <span className="muted" aria-live="polite">{data.count} {label.toLowerCase()} · Page {page} of {Math.max(1, Math.ceil(data.count / size))}</span>
    <div className="actions">
      <button type="button" className="btn secondary" aria-label={`Previous page of ${label.toLowerCase()}`}
        disabled={!data.previous || page <= 1} onClick={() => change(page - 1)}>Previous</button>
      <button type="button" className="btn secondary" aria-label={`Next page of ${label.toLowerCase()}`}
        disabled={!data.next} onClick={() => change(page + 1)}>Next</button>
    </div>
  </nav>;
}

export function Status({ status }: { status: BookingStatus }) {
  return <span className={`badge fd-status fd-status-${status}`}>{statusLabel[status] ?? status}</span>;
}

// History payloads are arrays in v1; bound rendered rows without truncating the response.
export function HistoryList<T>({ title, entries, render, empty }: {
  title: string; entries: T[]; render: (item: T) => ReactNode; empty: string;
}) {
  const [page, setPage] = useState(1);
  const size = 10;
  const start = (page - 1) * size;
  return <section className="fd-stack"><h3>{title}</h3>
    {entries.length ? <>
      <ol className="fd-history" start={start + 1}>
        {entries.slice(start, start + size).map((entry, i) => <li key={start + i}>{render(entry)}</li>)}
      </ol>
      {entries.length > size && <Pager label={title} size={size} page={page} change={setPage}
        data={{ count: entries.length, previous: page > 1 ? 'previous' : null, next: start + size < entries.length ? 'next' : null }} />}
    </> : <p className="empty">{empty}</p>}
  </section>;
}

export function Dialog({ title, children, onClose, busy = false, wide = false }: {
  title: string; children: ReactNode; onClose: () => void; busy?: boolean; wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const id = useId();
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const opener = document.activeElement;
    if (!node.open) {
      if (typeof node.showModal === 'function') node.showModal();
      else node.setAttribute('open', '');
    }
    heading.current?.focus({ preventScroll: true });
    return () => {
      if (typeof node.close === 'function' && node.open) node.close();
      queueMicrotask(() => {
        if (document.querySelector('dialog[open]')) return;
        const target = opener instanceof HTMLElement && opener.isConnected && opener !== document.body && !opener.matches(':disabled')
          ? opener : document.querySelector<HTMLElement>('.fd-page h1');
        target?.focus({ preventScroll: true });
      });
    };
  }, []);
  return <dialog ref={ref} className={`fd-dialog${wide ? ' fd-dialog-wide' : ''}`} aria-labelledby={id} aria-modal="true"
    onCancel={event => { event.preventDefault(); if (!busy) onClose(); }} onKeyDown={event => {
      if (typeof event.currentTarget.showModal === 'function') return; // Native modal handles focus containment and Escape.
      if (event.key === 'Escape') { event.preventDefault(); if (!busy) onClose(); }
      if (event.key !== 'Tab') return;
      const items = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled)'));
      const index = items.indexOf(document.activeElement as HTMLElement);
      if (!items.length || (event.shiftKey ? index <= 0 : index === items.length - 1)) {
        event.preventDefault(); (event.shiftKey ? items.at(-1) : items[0])?.focus();
      }
    }}>
    <div className="fd-dialog-inner"><div className="fd-dialog-header">
      <h2 ref={heading} id={id} tabIndex={-1}>{title}</h2>
      <button type="button" className="btn secondary" onClick={onClose} disabled={busy} aria-label={`Close ${title}`}>Close</button>
    </div>{children}</div>
  </dialog>;
}
