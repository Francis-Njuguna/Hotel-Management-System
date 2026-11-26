import { useState, type FormEvent } from 'react';
import { ArrowLeft, ArrowRight, CheckCircle2, MailCheck } from 'lucide-react';
import { Link, Navigate, useLocation, useParams } from 'react-router-dom';
import { z } from 'zod';
import { send, type SessionUser } from '../../services/api';
import { useSession } from '../../services/session';
import { resumePath } from '../../app/navigation';
import { LoadingState } from '../../app/States';
import { AuthFrame, AuthResult, httpStatus, SecretField, useCommand } from './AuthFrame';

const credentials = z.object({ username: z.string().trim().min(1, 'Enter your staff username.'), password: z.string().min(1, 'Enter your password.') });
const emailAddress = z.string().trim().email('Enter a valid staff email address.');

export function LoginPage() {
  const { user, refresh, loading } = useSession();
  const { state } = useLocation();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [fields, setFields] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const { pending, run } = useCommand();
  if (user) return <Navigate to={resumePath(state?.from)} replace />;
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    const parsed = credentials.safeParse({ username, password });
    if (!parsed.success) {
      const errors = Object.fromEntries(parsed.error.issues.map((issue) => [String(issue.path[0]), issue.message]));
      setFields(errors); document.getElementById(Object.keys(errors)[0])?.focus(); return;
    }
    setFields({});
    void run(async () => {
      try {
        const result = await send<{ user: SessionUser | null }>('auth/login/', 'POST', parsed.data);
        if (!result.user) { setError('Sign-in was not accepted. Check your username and password and try again.'); return; }
        await refresh(); // Navigate only when the verified session actually changes.
      } catch (cause) {
        const status = httpStatus(cause);
        setError(status === 429 ? 'Too many sign-in attempts. Wait a moment, then try again.'
          : status === 400 || status === 401 || status === 403 ? 'Sign-in was not accepted. Check your username and password and try again.'
          : 'Could not complete sign-in. Check your connection and credentials, then try again.');
      }
    });
  }
  return <AuthFrame title="Staff sign in" description="Use your assigned username and password to open your workspace.">
    {state?.signedOut && <p className="notice" role="status">You have signed out.</p>}
    {loading ? <LoadingState label="Checking your session…" /> : <form className="auth-form" onSubmit={submit} noValidate aria-busy={pending}>
      <div className="field"><label htmlFor="username">Username</label><input id="username" name="username" autoComplete="username" autoCapitalize="none" spellCheck={false}
        value={username} onChange={(event) => setUsername(event.target.value)} required aria-invalid={Boolean(fields.username)} aria-describedby={fields.username ? 'username-error' : undefined} />
        {fields.username && <span role="alert" id="username-error" className="field-error">{fields.username}</span>}
      </div>
      <SecretField id="password" label="Password" value={password} change={setPassword} completion="current-password" error={fields.password} />
      <Link className="auth-recovery" to="/reset">Forgot password?</Link>
      {error && <div className="error" role="alert">{error}</div>}
      <button className="btn primary auth-submit" type="submit" disabled={pending}>{pending ? 'Signing in…' : 'Sign in'}<ArrowRight size={17} aria-hidden="true" /></button>
    </form>}
  </AuthFrame>;
}

function BackToSignIn() {
  return <Link className="back-to-login" to="/login"><ArrowLeft size={16} aria-hidden="true" /> Back to sign in</Link>;
}

export function RequestResetPage() {
  const { loading } = useSession();
  const [email, setEmail] = useState('');
  const [fieldError, setFieldError] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const { pending, run } = useCommand();
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError('');
    const parsed = emailAddress.safeParse(email);
    if (!parsed.success) { setFieldError('Enter a valid staff email address.'); document.getElementById('reset-email')?.focus(); return; }
    setFieldError('');
    void run(async () => {
      try { await send('auth/reset/', 'POST', { email: parsed.data }); setDone(true); setEmail(''); }
      catch (cause) { setError(httpStatus(cause) === 429 ? 'Too many requests. Wait a moment before trying again.' : 'Could not submit the request. Check your connection and try again.'); }
    });
  }
  return <AuthFrame title="Reset your password" description="Request a reset link using the verified recovery email on your staff account.">
    {loading ? <LoadingState label="Preparing password recovery…" /> : done ? <AuthResult icon={MailCheck} title="Check your inbox">If an eligible account matches, you’ll receive an email with a reset link. Check your spam folder as well.</AuthResult>
      : <form onSubmit={submit} className="auth-form" noValidate aria-busy={pending}>
        <div className="field"><label htmlFor="reset-email">Staff email</label><input id="reset-email" name="email" type="email" autoComplete="email" required spellCheck={false}
          value={email} onChange={(event) => setEmail(event.target.value)} aria-invalid={Boolean(fieldError)} aria-describedby={fieldError ? 'email-error' : undefined} />
          {fieldError && <span role="alert" className="field-error" id="email-error">{fieldError}</span>}
        </div>{error && <div className="error" role="alert">{error}</div>}
        <button type="submit" className="btn primary auth-submit" disabled={pending}>{pending ? 'Requesting link…' : 'Request reset link'}<ArrowRight size={17} aria-hidden="true" /></button>
      </form>}
    <BackToSignIn />
  </AuthFrame>;
}

export function ConfirmResetPage() {
  const { uid, token } = useParams();
  const { loading, refresh } = useSession();
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [fields, setFields] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const { pending, run } = useCommand();
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError('');
    const errors: Record<string, string> = {};
    if (password.length < 8 || password.length > 128) errors['new-password'] = 'Use a password between 8 and 128 characters.';
    if (!confirm || confirm !== password) errors['confirm-password'] = 'Enter the same password in both fields.';
    setFields(errors);
    if (Object.keys(errors).length) { document.getElementById(Object.keys(errors)[0])?.focus(); return; }
    void run(async () => {
      try {
        await send('auth/reset/confirm/', 'POST', { uid, token, password });
        setDone(true); setPassword(''); setConfirm(''); await refresh();
      }
      catch (cause) {
        const status = httpStatus(cause);
        const data = cause && typeof cause === 'object' && 'data' in cause ? cause.data : null;
        if (status === 400 && data && typeof data === 'object' && 'password' in data) {
          setFields({ 'new-password': 'This password does not meet your account’s password policy. Try a longer, less common passphrase that is unrelated to your staff details.' });
          document.getElementById('new-password')?.focus();
        } else if (status === 400 && data && typeof data === 'object' && 'detail' in data && data.detail === 'Invalid or expired reset link.') {
          setError('This reset link is invalid or has expired. Request a fresh link to continue.');
        } else {
          setError(status === 429 ? 'Too many requests. Wait a moment before trying again.' : 'Could not change the password. Check your connection and try again, or request a fresh link.');
        }
      }
    });
  }
  return <AuthFrame title="Set a new password" description="Choose a long, unique password for your staff account.">
    {loading ? <LoadingState label="Preparing password recovery…" /> : done ? <AuthResult icon={CheckCircle2} title="Password changed">You can now sign in with your new password.</AuthResult> : <form className="auth-form" noValidate onSubmit={submit} aria-busy={pending}>
      <SecretField id="new-password" label="New password" value={password} change={setPassword} completion="new-password" error={fields['new-password']} />
      <SecretField id="confirm-password" label="Confirm password" value={confirm} change={setConfirm} completion="new-password" error={fields['confirm-password']} />
      {error && <div className="error" role="alert">{error} <Link to="/reset">Request a new link</Link></div>}
      <button type="submit" className="btn primary auth-submit" disabled={pending}>{pending ? 'Saving password…' : 'Save new password'}<ArrowRight size={17} aria-hidden="true" /></button>
    </form>}
    <BackToSignIn />
  </AuthFrame>;
}
