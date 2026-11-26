import { Component, lazy, Suspense, type ReactNode } from 'react';
import { ArrowLeft, Compass, ShieldCheck } from 'lucide-react';
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useSession } from '../services/session';
import { ConfirmResetPage, LoginPage, RequestResetPage } from '../features/auth/AuthPages';
import { VerifyRecoveryEmailPage } from '../features/auth/RecoveryEmail';
import { useCommand } from '../features/auth/AuthFrame';
import { OverviewPage } from '../features/dashboard/OverviewPage';
import { InboxPage } from '../features/dashboard/InboxPage';
import { Brand } from './Identity';
import { canOpen, linksFor, type WorkspaceKey } from './navigation';
import { FailureState, LoadingState } from './States';
import { Workspace } from './Workspace';

const Guests = lazy(() => import('../features/frontdesk').then((m) => ({ default: m.GuestsPage })));
const Rooms = lazy(() => import('../features/frontdesk').then((m) => ({ default: m.RoomsPage })));
const Reservations = lazy(() => import('../features/frontdesk').then((m) => ({ default: m.ReservationsPage })));
const Housekeeping = lazy(() => import('../features/operations').then((m) => ({ default: m.HousekeepingPage })));
const Restaurant = lazy(() => import('../features/operations').then((m) => ({ default: m.RestaurantPage })));
const Parking = lazy(() => import('../features/operations').then((m) => ({ default: m.ParkingPage })));
const Billing = lazy(() => import('../features/office').then((m) => ({ default: m.BillingPage })));
const Staff = lazy(() => import('../features/office').then((m) => ({ default: m.StaffPage })));

function WorkspaceGate() {
  const { user } = useSession();
  const { pathname, search, hash } = useLocation();
  return user ? <Workspace user={user} key={`${user.id}:${user.capabilities.join(',')}`} />
    : <Navigate to="/login" replace state={{ from: pathname + search + hash }} />;
}

function Unavailable({ denied }: { denied?: boolean }) {
  const { user } = useSession();
  const home = linksFor(user)[0];
  const Icon = denied ? ShieldCheck : Compass;
  return <section className="page"><div className="panel unavailable"><span className="quiet-empty-icon"><Icon size={25} aria-hidden="true" /></span>
    <span className="eyebrow">{denied ? 'Staff access' : 'Page not found'}</span>
    <h1>{denied ? 'This workspace isn’t available to you' : 'We couldn’t find that page'}</h1>
    <p>{denied ? 'Your staff account does not have access to this area. Contact your administrator if you need to use it.' : 'Check the address, or choose a workspace from the navigation.'}</p>
    {home && <Link to={home.path} className="btn secondary"><ArrowLeft size={16} aria-hidden="true" />Go to {home.label.toLowerCase()}</Link>}
  </div></section>;
}

/** The guard runs before any lazy module or its data loaders mount. Server controls remain authoritative. */
export function AccessGate({ area, children }: { area: WorkspaceKey; children: ReactNode }) {
  const { user } = useSession();
  return canOpen(user, area) ? <PageBoundary key={area}><Suspense fallback={<LoadingState label="Opening workspace…" />}>{children}</Suspense></PageBoundary> : <Unavailable denied />;
}

class PageBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? <div className="page"><FailureState title="This workspace could not be opened" message="Retry to reload the application and request a fresh copy." retry={() => window.location.reload()} /></div> : this.props.children;
  }
}

export function App() {
  const { loading, error, refresh } = useSession();
  const { pending, run } = useCommand();
  if (loading || error) return <main className="session-screen"><Brand /><div className="session-status">
    {loading || pending ? <LoadingState label="Checking your staff session…" /> : <FailureState title="The session service is unavailable" message="Check your connection and retry to verify your staff session." retry={() => { void run(refresh); }} />}
  </div></main>;
  return <Routes>
    <Route path="/login" element={<LoginPage />} /><Route path="/reset" element={<RequestResetPage />} />
    <Route path="/reset/:uid/:token" element={<ConfirmResetPage />} />
    <Route element={<WorkspaceGate />}>
      <Route path="verify-email/:token?" element={<VerifyRecoveryEmailPage />} />
      <Route index element={<AccessGate area="overview"><OverviewPage /></AccessGate>} />
      <Route path="reservations" element={<AccessGate area="reservations"><Reservations /></AccessGate>} />
      <Route path="guests" element={<AccessGate area="guests"><Guests /></AccessGate>} />
      <Route path="rooms" element={<AccessGate area="rooms"><Rooms /></AccessGate>} />
      <Route path="housekeeping" element={<AccessGate area="housekeeping"><Housekeeping /></AccessGate>} />
      <Route path="restaurant" element={<AccessGate area="restaurant"><Restaurant /></AccessGate>} />
      <Route path="parking" element={<AccessGate area="parking"><Parking /></AccessGate>} />
      <Route path="billing" element={<AccessGate area="billing"><Billing /></AccessGate>} />
      <Route path="staff" element={<AccessGate area="staff"><Staff /></AccessGate>} />
      <Route path="notifications" element={<AccessGate area="notifications"><InboxPage /></AccessGate>} />
      <Route path="*" element={<Unavailable />} />
    </Route>
  </Routes>;
}
