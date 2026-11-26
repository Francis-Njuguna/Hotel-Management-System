import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Bell, ChevronRight, Clock3, Menu, PanelLeft, X } from 'lucide-react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import type { SessionUser } from '../services/api';
import { SignOutButton } from '../features/auth/SignOutButton';
import { RequestVerification } from '../features/auth/RecoveryEmail';
import { Brand } from './Identity';
import { canOpen, initials, isVerificationLink, linksFor, navigationGroups } from './navigation';

const narrow = '(max-width: 63.99rem)';
function subscribeLayout(listener: () => void) {
  const media = window.matchMedia?.(narrow);
  media?.addEventListener('change', listener);
  return () => media?.removeEventListener('change', listener);
}
const isNarrow = () => window.matchMedia?.(narrow).matches ?? false;
const propertyTime = new Intl.DateTimeFormat('en-GB', { timeZone: 'Africa/Nairobi', hour: '2-digit', minute: '2-digit' });

function PropertyClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => { const timer = window.setInterval(() => setNow(new Date()), 30_000); return () => window.clearInterval(timer); }, []);
  return <div className="property-clock"><Clock3 size={15} aria-hidden="true" /><span>Property time</span>
    <time dateTime={now.toISOString()}>{propertyTime.format(now)} EAT</time></div>;
}

function Rail({ user, close }: { user: SessionUser; close?: () => void }) {
  const links = linksFor(user).filter(({ key }) => key !== 'notifications'); // Inbox has a persistent top-bar shortcut.
  const name = user.full_name.trim() || user.username;
  return <div className="rail-interior">
    <div className="rail-masthead"><Brand />{close && <button className="rail-close" type="button" aria-label="Close navigation" onClick={close}><X size={20} aria-hidden="true" /></button>}</div>
    <nav className="rail-nav" aria-label="Main navigation">{navigationGroups.map((group) => {
      const groupLinks = links.filter((entry) => entry.group === group);
      return groupLinks.length > 0 && <div className="rail-group" key={group}><p>{group}</p><ul>
        {groupLinks.map(({ key, icon: Icon, path, label }) => <li key={key}><NavLink end to={path} onClick={close}
          className={({ isActive }) => `rail-link${isActive ? ' selected' : ''}`}><Icon size={18} strokeWidth={1.75} aria-hidden="true" /><span>{label}</span></NavLink></li>)}
      </ul></div>;
    })}</nav>
    <footer className="rail-account"><div className="account-row"><span className="account-avatar" aria-hidden="true">{initials(name)}</span>
      <div className="account-details"><strong>{name}</strong><span>{user.roles.join(' · ') || 'Staff account'}</span></div>
    </div><div className="account-actions"><RequestVerification rail /><SignOutButton /></div></footer>
  </div>;
}

function Drawer({ user, close }: { user: SessionUser; close: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    dialog.showModal(); // Browser handles the focus trap, inert background and focus return.
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { dialog.close(); document.body.style.overflow = previous; };
  }, []);
  return <dialog ref={ref} className="workspace-rail rail-drawer" aria-label="Workspace menu" id="workspace-drawer"
    onCancel={(event) => { event.preventDefault(); close(); }} onClick={(event) => { if (event.target === ref.current) close(); }}>
    <Rail user={user} close={close} />
  </dialog>;
}

export function Workspace({ user }: { user: SessionUser }) {
  const { pathname } = useLocation();
  const mobile = useSyncExternalStore(subscribeLayout, isNarrow, () => false);
  const [drawer, setDrawer] = useState(false);
  const main = useRef<HTMLElement>(null);
  const previousPath = useRef(pathname);
  const current = linksFor(user).find(({ path }) => path === (pathname.replace(/\/$/, '') || '/'));
  const title = current?.label ?? (isVerificationLink(pathname) || pathname === '/verify-email' ? 'Recovery email' : 'Workspace');
  useEffect(() => {
    document.title = `${title} · Hotel A Front Office`;
    if (previousPath.current !== pathname) { previousPath.current = pathname; setDrawer(false); main.current?.focus(); }
  }, [pathname, title]);
  useEffect(() => { if (!mobile) setDrawer(false); }, [mobile]);
  return <div className="workspace">
    <a href="#main-content" className="skip-link">Skip to content</a>
    {mobile ? drawer && <Drawer user={user} close={() => setDrawer(false)} /> : <aside className="workspace-rail desktop-rail"><Rail user={user} /></aside>}
    <div className="workspace-body"><header className="workspace-bar">
      <div className="bar-location">{mobile ? <button type="button" className="icon-button mobile-menu" aria-label="Open navigation" aria-haspopup="dialog"
        aria-expanded={drawer} aria-controls={drawer ? 'workspace-drawer' : undefined} onClick={() => setDrawer(true)}><Menu size={21} aria-hidden="true" /></button>
        : <PanelLeft className="bar-location-icon" size={17} strokeWidth={1.7} aria-hidden="true" />}
        <span className="breadcrumb-parent">{mobile ? 'Hotel A' : 'Staff workspace'}</span><ChevronRight size={14} className="crumb-chevron" aria-hidden="true" />
        <div className="bar-current">{mobile && <small className="bar-mobile-brand">Hotel A · Front Office</small>}<strong>{title}</strong></div>
      </div>
      <div className="bar-tools"><PropertyClock />{canOpen(user, 'notifications') && <Link className={`icon-button inbox-shortcut${current?.key === 'notifications' ? ' active' : ''}`}
        aria-label="Open notifications" title="Notifications" to="/notifications"><Bell size={18} aria-hidden="true" /></Link>}</div>
    </header><main id="main-content" ref={main} tabIndex={-1} className="workspace-main"><Outlet /></main></div>
  </div>;
}
