import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { type Collection } from './data';
import { statusText } from './format';
import './operations.css';

export function PageHeader({ title, children }: { title: string; children: ReactNode }) {
  return <header className="page-header"><div><span className="eyebrow">Hotel operations</span>
    <h1>{title}</h1><p className="muted">{children}</p></div></header>;
}

export function Switcher<T extends string>({ label, value, options, change }: {
  label: string; value: T; options: { value: T; label: string }[]; change: (value: T) => void;
}) {
  if (options.length < 2) return null;
  return <div role="group" aria-label={label} className="ops-switch">
    {options.map((option) => <button key={option.value} type="button" className="btn secondary"
      aria-pressed={option.value === value} onClick={() => change(option.value)}>{option.label}</button>)}
  </div>;
}

export function Notice({ text }: { text: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // A saved form or transitioned row may have just unmounted beneath keyboard focus.
    if (text && document.activeElement === document.body) ref.current?.focus();
  }, [text]);
  return <div ref={ref} tabIndex={-1} role="status" aria-live="polite" aria-atomic="true" className={text ? 'ops-feedback' : 'visually-hidden'}>
    {text && <p className="notice">{text}</p>}</div>;
}

export function Problem({ text, focus = false }: { text: string; focus?: boolean }) {
  const ref = useRef<HTMLParagraphElement>(null);
  useEffect(() => { if (text && focus) ref.current?.focus(); }, [text, focus]);
  return text ? <p className="error ops-feedback" role="alert" tabIndex={focus ? -1 : undefined} ref={ref}>{text}</p> : null;
}

export function Status({ value }: { value: string }) {
  return <span className="badge ops-badge" data-state={value}>{statusText(value)}</span>;
}

export function FormHeading({ children, hint }: { children: ReactNode; hint?: string }) {
  const ref = useRef<HTMLHeadingElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);
  return <div className="ops-form-heading"><h3 tabIndex={-1} ref={ref}>{children}</h3>
    {hint && <p className="muted">{hint}</p>}</div>;
}

export function FormActions({ busy, submit, cancel }: { busy: boolean; submit: string; cancel: () => void }) {
  return <div className="actions ops-actions"><button type="submit" disabled={busy} className="btn primary">
    {busy ? 'Saving…' : submit}</button><button type="button" className="btn secondary" onClick={cancel}
    disabled={busy}>Cancel</button></div>;
}

export function Pager<T>({ list, name }: { list: Collection<T>; name: string }) {
  const { data, page, size, go } = list;
  if (!data || (!data.previous && !data.next)) return null;
  return <div className="ops-pager" role="group" aria-label={`${name} pagination`}>
    <button className="btn secondary" type="button" disabled={!data.previous} onClick={() => go(page - 1)}
      aria-label={`Previous page of ${name}`}>Previous</button>
    <span className="muted">{(page - 1) * size + 1}–{Math.min(page * size, data.count)} of {data.count}</span>
    <button className="btn secondary" type="button" disabled={!data.next} onClick={() => go(page + 1)}
      aria-label={`Next page of ${name}`}>Next</button>
  </div>;
}

export function LoadState<T>({ list, name, empty, children }: {
  list: Collection<T>; name: string; empty: string; children: (rows: T[]) => ReactNode;
}) {
  if (list.loading) return <p className="muted" role="status">Loading {name}…</p>;
  if (list.error || !list.data) return <div className="ops-error-block">
    <Problem text={list.error || `Could not load ${name}.`} /><div className="actions">
      <button type="button" className="btn secondary" onClick={list.retry}>Retry loading {name}</button>
      {list.page > 1 && <button type="button" className="btn secondary" onClick={() => list.go(1)}>Go to first page</button>}
    </div></div>;
  if (!list.data.results.length) return <div className="empty" role="status">{empty}</div>;
  return <>{children(list.data.results)}<Pager list={list} name={name} /></>;
}

/** Also used in pickers inside a form: Enter searches, it never submits the enclosing command. */
export function SearchBox({ label, value, change }: { label: string; value: string; change: (s: string) => void }) {
  const id = useId();
  const [draft, setDraft] = useState(value);
  const apply = () => change(draft.trim());
  return <div className="field ops-search"><label htmlFor={id}>{label}</label><div className="ops-inline">
    <input type="search" enterKeyHint="search" maxLength={160} id={id} value={draft} onChange={(e) => setDraft(e.target.value)}
      onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); apply(); } }} />
    <button type="button" className="btn secondary" onClick={apply}>Search</button>
    {(draft || value) && <button type="button" className="btn secondary" onClick={() => { setDraft(''); change(''); }}>Clear</button>}
  </div></div>;
}

export function StatusFilter({ value, change, options, label = 'Status' }: {
  value: string; change: (s: string) => void; options: readonly string[]; label?: string;
}) {
  return <label className="field"><span>{label}</span><select value={value} onChange={(e) => change(e.target.value)}>
    <option value="">All statuses</option>{options.map((s) => <option value={s} key={s}>{statusText(s)}</option>)}
  </select></label>;
}

export function Refresh({ onClick }: { onClick: () => void }) {
  return <button type="button" className="btn secondary" onClick={onClick}>Refresh list</button>;
}

export function ConfirmAction({ label, question, confirm, busy, execute }: {
  label: string; question: string; confirm: string; busy: boolean; execute: () => void;
}) {
  const [asking, setAsking] = useState(false);
  const id = useId();
  const ref = useRef<HTMLButtonElement>(null);
  const opener = useRef<HTMLButtonElement>(null);
  useEffect(() => { if (asking) ref.current?.focus(); }, [asking]);
  return <div className="ops-confirm"><button ref={opener} type="button" className="btn secondary"
    disabled={busy} aria-expanded={asking} aria-controls={asking ? id : undefined} onClick={() => setAsking((v) => !v)}>{label}</button>
    {asking && <div id={id} className="ops-confirm-body" role="group" aria-label={question}>
      <p>{question}</p><div className="actions"><button type="button" className="btn primary" disabled={busy}
        ref={ref} onClick={execute}>{busy ? 'Saving…' : confirm}</button>
        <button type="button" className="btn secondary" disabled={busy} onClick={() => {
          setAsking(false); opener.current?.focus();
        }}>Keep unchanged</button></div></div>}
  </div>;
}
