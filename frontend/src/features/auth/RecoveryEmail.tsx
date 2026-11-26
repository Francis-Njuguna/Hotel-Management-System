import { useState } from 'react';
import { ArrowRight, CheckCircle2, MailCheck, ShieldCheck, UserRound } from 'lucide-react';
import { Link, Navigate, useLocation, useNavigate, useParams } from 'react-router-dom';
import { send, type SessionUser } from '../../services/api';
import { useSession } from '../../services/session';
import { linksFor } from '../../app/navigation';
import { AuthResult, httpStatus, useCommand } from './AuthFrame';

/** No editable address: the server selects the current staff account's stored address. */
export function RequestVerification({ rail = false }: { rail?: boolean }) {
  const { user } = useSession();
  const [requested, setRequested] = useState(false);
  const [error, setError] = useState('');
  const { pending, run } = useCommand();
  if (!user) return null;
  function request() {
    void run(async () => {
      setError(''); setRequested(false);
      try { await send<{ detail: string }>('auth/recovery-email/', 'POST', {}); setRequested(true); }
      catch (cause) {
        const status = httpStatus(cause);
        setError(status === 429 ? 'Please wait before requesting another link.'
          : status === 400 ? 'A verification link could not be requested. Ask your administrator to check the recovery address on your staff account.'
          : status === 503 ? 'Verification email is unavailable. Ask your administrator to check mail delivery.'
          : 'Could not request a verification email. Check your connection and try again.');
      }
    });
  }
  return <div className={rail ? 'rail-verification' : 'verification-request'}>
    <button type="button" className={rail ? 'rail-account-action' : 'btn secondary'} disabled={pending} onClick={request}
      title="Send a verification link to the recovery address on your staff account"><MailCheck size={16} aria-hidden="true" />
      {pending ? 'Requesting link…' : 'Send verification email'}</button>
    <div role="status" aria-atomic="true">{requested && <p className={rail ? 'account-feedback' : 'notice'}>If your account has an eligible recovery address, check its inbox for a verification link.</p>}</div>
    {error && <p role="alert" className={rail ? 'account-feedback account-failure' : 'error'}>{error}</p>}
  </div>;
}

function ConfirmAddress({ token, user, confirmed }: { token: string; user: SessionUser; confirmed: () => void }) {
  const [error, setError] = useState('');
  const { pending, run } = useCommand();
  function confirm() {
    void run(async () => {
      setError('');
      try {
        // Never decode the token into an identity or verify on visit. The endpoint binds it to the signed-in staff member.
        await send('auth/recovery-email/confirm/', 'POST', { token });
        confirmed();
      } catch (cause) {
        const status = httpStatus(cause);
        setError(status === 400 || status === 403 || status === 404 || status === 410
          ? 'This link could not be confirmed for this staff account. Check the signed-in account or request a fresh verification email.'
          : status === 429 ? 'Too many attempts. Wait a moment before trying again.'
          : 'Could not confirm verification. Check your connection and retry.');
      }
    });
  }
  return <>
    <div className="verification-identity"><UserRound size={19} aria-hidden="true" /><div><small>Signed in as</small><strong>{user.username}</strong></div></div>
    <p>Confirm only if this is the staff account that requested the link. To switch accounts, use Sign out in the navigation and sign in again.</p>
    {error && <p role="alert" className="error">{error}</p>}
    <div className="actions"><button className="btn primary" type="button" onClick={confirm} disabled={pending}>
      <ShieldCheck size={17} aria-hidden="true" />{pending ? 'Confirming email…' : 'Confirm recovery email'}</button></div>
    {error && <RequestVerification />}
  </>;
}

function Verified({ finish }: { finish: () => void }) {
  return <><AuthResult icon={CheckCircle2} title="Recovery email verified">This staff account can now use its verified address for password recovery.</AuthResult>
    <div className="actions"><button className="btn secondary" type="button" onClick={finish}>Done<ArrowRight size={16} aria-hidden="true" /></button></div></>;
}

export function VerifyRecoveryEmailPage() {
  const { user } = useSession();
  const { token } = useParams();
  const { key: visit } = useLocation();
  // This is a navigation entry key, not a token or an account verification flag read from the URL.
  const [confirmedVisit, setConfirmedVisit] = useState<string | null>(null);
  const navigate = useNavigate();
  if (!user) return null; // WorkspaceGate handles sign-in and the return path.
  if (token && confirmedVisit === visit) return <Navigate to="/verify-email" replace />;
  const home = linksFor(user)[0]?.path ?? '/';
  return <section className="page recovery-page"><header className="page-header"><div><span className="eyebrow">Account security</span>
    <h1>Verify recovery email</h1><p className="muted">Prove ownership of the address already on your staff account.</p></div></header>
    <div className="panel verification-panel"><div className="verification-heading"><span className="board-icon"><MailCheck size={21} aria-hidden="true" /></span><h2>Email ownership</h2></div>
      {token ? <ConfirmAddress key={visit} user={user} token={token} confirmed={() => setConfirmedVisit(visit)} />
        : confirmedVisit !== null ? <Verified finish={() => navigate(home, { replace: true })} /> : <>
        <p>Open the link sent to your recovery address, or request a new verification email.</p><RequestVerification /><Link to={home}>Return to workspace</Link></>}
    </div>
  </section>;
}
