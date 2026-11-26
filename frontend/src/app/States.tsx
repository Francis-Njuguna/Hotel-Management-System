import { AlertCircle, Inbox, LoaderCircle, RotateCw, type LucideIcon } from 'lucide-react';

export function LoadingState({ label }: { label: string }) {
  return <div className="app-state loading-state" role="status"><LoaderCircle aria-hidden="true" className="spinner" size={21} /><span>{label}</span></div>;
}

export function FailureState({ title, message, retry }: { title: string; message: string; retry: () => void }) {
  return <div className="app-state failure-state">
    <AlertCircle aria-hidden="true" size={22} />
    <div role="alert"><strong>{title}</strong><p>{message}</p></div>
    <button type="button" className="btn secondary" onClick={retry}><RotateCw size={15} aria-hidden="true" />Retry</button>
  </div>;
}

export function EmptyState({ title, children, icon: Icon = Inbox }: { title: string; children: string; icon?: LucideIcon }) {
  return <div className="quiet-empty"><span className="quiet-empty-icon"><Icon size={21} aria-hidden="true" /></span><div><strong>{title}</strong><p>{children}</p></div></div>;
}
