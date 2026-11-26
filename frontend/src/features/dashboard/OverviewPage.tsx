import { ArrowRight, CalendarDays, Compass, Layers, RefreshCw, Zap } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { SessionUser } from '../../services/api';
import { can, useSession } from '../../services/session';
import { HotelFacade } from '../../app/Identity';
import { canOpen, workspaceLink, type WorkspaceKey } from '../../app/navigation';
import { EmptyState, FailureState, LoadingState } from '../../app/States';
import { useResource } from '../../app/useResource';
import { calendarDate, decodeOverview } from './model';
import { Board } from './Panel';
import { indicators, OtherIndicators, Snapshot } from './Snapshot';
import { CleaningBoard, InvoiceBoard, MessagePreview, OrderBoard, RepairBoard, ReservationBoard } from './Worklists';

function shiftDescription(user: SessionUser) {
  if (can(user, 'reservations.view')) return 'Room movements, guest bookings and service queues for the day ahead.';
  if (can(user, 'restaurant.view')) return 'Follow service orders and pick up the next step in the kitchen.';
  if (can(user, 'housekeeping.view')) return 'Review your cleaning queue and move rooms toward inspection.';
  if (can(user, 'maintenance.view')) return 'Review your assigned work orders and room blocks.';
  if (can(user, 'billing.manage')) return 'Review charges, received tender and the invoice register.';
  return 'Your property briefing and the workspaces available to your account.';
}

function QuickActions({ user }: { user: SessionUser }) {
  const actions: Array<[WorkspaceKey, string]> = [['reservations', can(user, 'reservations.manage') ? 'Manage reservations' : 'View reservations'], ['rooms', 'Check room inventory'],
    ['housekeeping', can(user, 'housekeeping.view') ? 'Open task queues' : 'Open work orders'], ['billing', can(user, 'billing.manage') ? 'Review invoices' : 'Look up a folio'], ['guests', 'Find a guest'],
    ['restaurant', 'Open restaurant'], ['parking', can(user, 'parking.manage') ? 'Manage parking' : 'Review parking'], ['staff', can(user, 'staff.manage') ? 'Manage staff' : 'Review activity'], ['notifications', 'Read notifications']];
  return <Board title="Quick actions" kicker="Your workspace" icon={Zap} className="quick-board"><ul className="quick-links">
    {actions.filter(([key]) => canOpen(user, key)).slice(0, 4).map(([key, action]) => {
      const { description, path, icon: Icon } = workspaceLink(key, user);
      return <li key={key}><Link to={path}><span className="quick-icon"><Icon size={17} strokeWidth={1.8} aria-hidden="true" /></span>
        <span><strong>{action}</strong><small>{description}</small></span><ArrowRight className="quick-arrow" size={15} aria-hidden="true" /></Link></li>;
    })}</ul></Board>;
}

export function OverviewPage() {
  const { user } = useSession();
  // The route guard prevents mounting this data reader for denied users.
  return user && can(user, 'dashboard.view') ? <LiveOverview key={user.id} user={user} /> : null;
}

function LiveOverview({ user }: { user: SessionUser }) {
  const { data, loading, failed, reload, refreshed } = useResource('dashboard/', decodeOverview);
  const tiles = data ? indicators(data, user) : [];
  const showStays = Boolean(data?.reservations && can(user, 'reservations.view'));
  const showCleaning = Boolean(data?.tasks && can(user, 'housekeeping.view'));
  const showOrders = Boolean(data?.orders && can(user, 'restaurant.view'));
  const showRepairs = Boolean(data && can(user, 'maintenance.view'));
  const showInvoices = Boolean(data && can(user, 'billing.manage') && !can(user, 'reservations.view'));
  const hasWork = showStays || showCleaning || showOrders || showRepairs || showInvoices;
  return <div className="page dashboard-page">
    <header className="briefing"><div className="briefing-copy"><div className="briefing-kicker"><span /> Daily briefing</div>
      <h1>Operations overview</h1><p>{shiftDescription(user)}</p>
      <div className="briefing-tools">{data && <span className="briefing-date"><CalendarDays size={15} aria-hidden="true" /><time dateTime={data.date}>{calendarDate(data.date, true)}</time></span>}
        <button type="button" className="briefing-refresh" disabled={loading} onClick={reload} aria-label="Refresh overview"><RefreshCw size={14} aria-hidden="true" />Refresh</button></div>
    </div><div className="briefing-art" aria-hidden="true"><HotelFacade /></div></header>
    <span className="visually-hidden" role="status">{refreshed ? 'Shift overview refreshed.' : ''}</span>
    {loading && <div className="overview-pending"><LoadingState label="Loading your shift overview…" /><div className="skeleton-grid" aria-hidden="true"><i /><i /><i /><i /></div></div>}
    {failed && <FailureState title="The overview could not be loaded" message="Check your connection and retry. Your authorized workspaces are still available below." retry={reload} />}
    {data && <Snapshot items={tiles.slice(0, 4)} />}
    <div className={`brief-columns${!data ? ' brief-columns-pending' : ''}`}>
      {data && <div className="board-column work-column">
        {showStays && data.reservations && <ReservationBoard rows={data.reservations} date={data.date} />}
        {showCleaning && data.tasks && <CleaningBoard rows={data.tasks} />}
        {showOrders && data.orders && <OrderBoard rows={data.orders} />}
        {showRepairs && <RepairBoard featured={!tiles.length} />}{showInvoices && <InvoiceBoard />}
        {!hasWork && <Board title="Shift worklists" kicker="Operations" icon={Layers}>
          <EmptyState icon={Compass} title="No worklists in this briefing">Use the quick actions to open a workspace available to your account.</EmptyState></Board>}
      </div>}
      <div className="board-column context-column"><QuickActions user={user} />
        {data && <OtherIndicators items={tiles.slice(4)} />}
        {data?.notifications && <MessagePreview rows={data.notifications} />}
      </div>
    </div>
  </div>;
}
