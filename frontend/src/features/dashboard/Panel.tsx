import type { ReactNode } from 'react';
import { ArrowUpRight, type LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';
import { statusText } from './model';

export function Board({ title, kicker, icon: Icon, children, link, linkLabel, className = '' }: {
  title: string; kicker: string; icon: LucideIcon; children: ReactNode; link?: string; linkLabel?: string; className?: string;
}) {
  return <section className={`panel desk-board ${className}`} aria-label={title}>
    <div className="desk-board-head"><div className="board-identity"><span className="board-icon"><Icon size={20} strokeWidth={1.8} aria-hidden="true" /></span>
      <div><span className="board-kicker">{kicker}</span><h2>{title}</h2></div></div>
      {link && <Link className="board-open" to={link} aria-label={linkLabel ?? `Open ${title.toLowerCase()}`}><span>View all</span><ArrowUpRight size={15} aria-hidden="true" /></Link>}
    </div>{children}
  </section>;
}

export function StatusBadge({ value }: { value: string }) {
  return <span className="badge workflow-badge" data-status={value}><i aria-hidden="true" />{statusText(value)}</span>;
}
