import { useEffect, useRef, useState, type ReactNode } from 'react';
import { api, ApiError, type Page } from '../../services/api';

type ReadState<T> = { state: 'loading' } | { state: 'failed'; message: string } | { state: 'ready'; data: T };
type RequestState<T> = { value: ReadState<T>; retry: () => void };

function messageOf(cause: unknown) {
  return cause instanceof Error && cause.message ? cause.message : 'The server could not be reached.';
}

/** A new path or a retry never renders the preceding request's records. */
export function useRead<T>(path: string, decode: (raw: unknown) => T): RequestState<T> {
  const [revision, setRevision] = useState(0);
  const key = `${path}:${revision}`;
  const [result, setResult] = useState<{ key: string; value: ReadState<T> }>();

  useEffect(() => {
    const controller = new AbortController();
    void api<unknown>(path, { signal: controller.signal }).then(decode).then(
      data => { if (!controller.signal.aborted) setResult({ key, value: { state: 'ready', data } }); },
      cause => { if (!controller.signal.aborted) setResult({ key, value: { state: 'failed', message: messageOf(cause) } }); },
    );
    return () => controller.abort();
  }, [key, path, decode]);

  const value: ReadState<T> = result?.key === key ? result.value : { state: 'loading' };
  return { value, retry: () => setRevision(v => v + 1) };
}

export function ReadResult<T>({ request, label, children }: {
  request: RequestState<T>; label: string; children: (value: T) => ReactNode;
}) {
  const { value, retry } = request;
  if (value.state === 'loading') return <p className="muted" role="status">Loading {label}…</p>;
  if (value.state === 'failed') return <div>
    <p className="error" role="alert">Could not load {label}. {value.message}</p>
    <button type="button" className="btn secondary" onClick={retry}>Retry</button>
  </div>;
  return <>{children(value.data)}</>;
}

export function Pagination<T>({ page, data, onPage, label }: {
  page: number; data: Page<T>; onPage: (page: number) => void; label: 'Invoices' | 'Accounts' | 'Events' | 'Payments';
}) {
  const noun = label.toLowerCase();
  return <nav className="toolbar" aria-label={`${label} pagination`}>
    <span className="muted" role="status">Page {page} · {data.count} {data.count === 1 ? noun.slice(0, -1) : noun}</span>
    <div className="actions">
      <button type="button" className="btn secondary" disabled={page <= 1 || !data.previous}
        onClick={() => onPage(page - 1)}>Previous</button>
      <button type="button" className="btn secondary" disabled={!data.next}
        onClick={() => onPage(page + 1)}>Next</button>
    </div>
  </nav>;
}

export function useListing() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  function filter(text: string) { setSearch(text.trim()); setPage(1); }
  const params = new URLSearchParams({ page: String(page) });
  if (search) params.set('search', search);
  return { page, setPage, search, filter, params: params.toString() };
}
export type Listing = ReturnType<typeof useListing>;

export function SearchBox({ label, hint, listing }: { label: string; hint: string; listing: Listing }) {
  const [draft, setDraft] = useState(listing.search);
  return <form className="toolbar" role="search" aria-label={label} onSubmit={e => { e.preventDefault(); listing.filter(draft); }}>
    <label className="field">{label}<input type="search" value={draft} onChange={e => setDraft(e.target.value)} placeholder={hint} /></label>
    <div className="actions"><button type="submit" className="btn secondary">Search</button>
      {(draft || listing.search) && <button type="button" className="btn secondary" onClick={() => { setDraft(''); listing.filter(''); }}>Clear</button>}
    </div>
  </form>;
}

/** Lock synchronously (including double clicks) and ignore completions after leaving the form. */
export function useCommand() {
  const lock = useRef(false);
  const mounted = useRef(true);
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<{ message: string; status?: number } | null>(null);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  async function run<T>(write: () => Promise<T>, onSuccess: (result: T) => void) {
    if (lock.current) return;
    lock.current = true;
    setPending(true);
    setFailure(null);
    try {
      const result = await write();
      if (mounted.current) onSuccess(result);
    } catch (cause) {
      if (mounted.current) setFailure({ message: messageOf(cause), status: cause instanceof ApiError ? cause.status : undefined });
    } finally {
      lock.current = false;
      if (mounted.current) setPending(false);
    }
  }
  return { pending, failure, run, clearError: () => setFailure(null) };
}

export function SectionHeading({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLHeadingElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);
  return <h2 ref={ref} tabIndex={-1}>{children}</h2>;
}
