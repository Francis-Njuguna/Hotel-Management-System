import { useRef, useState } from 'react';
import { Bell, Check, ChevronLeft, ChevronRight, Mail, MailOpen, RefreshCw } from 'lucide-react';
import { send } from '../../services/api';
import { EmptyState, FailureState, LoadingState } from '../../app/States';
import { useResource } from '../../app/useResource';
import { decodeNotifications, propertyTimestamp } from './model';

const pageSize = 12;
export function InboxPage() {
  const [page, setPage] = useState(1);
  const { data, loading, failed, reload, refreshed } = useResource(`notifications/?page=${page}&page_size=${pageSize}`, decodeNotifications);
  const lock = useRef(false);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  async function markRead(id: number) {
    if (lock.current) return;
    lock.current = true; setBusy(id); setError(''); setSuccess('');
    try { await send(`notifications/${id}/read/`, 'POST', {}); setSuccess('Notification marked as read.'); reload(); }
    catch { setError('The update could not be confirmed. Refresh to check the message or try marking it as read again.'); }
    finally { setBusy(null); lock.current = false; }
  }
  function changePage(nextPage: number) { setSuccess(''); setError(''); setPage(nextPage); }
  return <section className="page inbox-page"><header className="page-header"><div><span className="eyebrow">Staff inbox</span>
    <h1>Notifications</h1><p className="muted">Messages addressed to your staff account, newest first.</p></div>
    <button className="btn secondary" type="button" disabled={loading || busy !== null} onClick={() => { setError(''); setSuccess(''); reload(); }}><RefreshCw size={15} aria-hidden="true" />Refresh</button></header>
    {error && <p className="error" role="alert">{error}</p>}<div role="status" className={success ? 'notice' : 'visually-hidden'}>{success || (refreshed ? 'Inbox refreshed.' : '')}</div>
    <div className="panel inbox-panel" aria-label="Recipient notifications">
      {loading && <LoadingState label="Loading your notifications…" />}
      {failed && <><FailureState title="Inbox unavailable" message="Notifications could not be loaded. Check your connection and retry." retry={reload} />
        {page > 1 && <button type="button" className="btn secondary" onClick={() => changePage(1)}>Return to first page</button>}</>}
      {data && <>{data.results.length ? <ul className="inbox-list">{data.results.map((message) => <li key={message.id}>
        <div className={`inbox-icon${message.read_at ? '' : ' unread'}`}>{message.read_at ? <MailOpen size={20} aria-hidden="true" /> : <Mail size={20} aria-hidden="true" />}</div>
        <article><div className="inbox-meta"><span className={`inbox-status${message.read_at ? '' : ' unread'}`}>{message.read_at ? 'Read' : 'Unread'}</span>
          {message.created_at && <time dateTime={message.created_at}>{propertyTimestamp(message.created_at)}</time>}</div>
          <h2>{message.title}</h2><p>{message.message}</p></article>
        {!message.read_at && <button type="button" className="btn secondary" disabled={busy !== null} onClick={() => void markRead(message.id)} aria-label={`Mark ${message.title} as read`}>
          <Check size={15} aria-hidden="true" />{busy === message.id ? 'Saving…' : 'Mark as read'}</button>}
      </li>)}</ul> : <EmptyState title="Your inbox is empty" icon={Bell}>Messages addressed to you will appear here. No action is needed.</EmptyState>}
        <nav className="inbox-pager" aria-label="Notification pages"><span>{data.count} {data.count === 1 ? 'message' : 'messages'} · Page {page} of {Math.max(1, Math.ceil(data.count / pageSize))}</span>
          <div className="actions"><button type="button" className="btn secondary" disabled={!data.previous || busy !== null} onClick={() => changePage(Math.max(1, page - 1))}><ChevronLeft size={15} aria-hidden="true" />Previous</button>
            <button type="button" className="btn secondary" disabled={!data.next || busy !== null} onClick={() => changePage(page + 1)}>Next<ChevronRight size={15} aria-hidden="true" /></button></div></nav>
      </>}
    </div>
  </section>;
}
