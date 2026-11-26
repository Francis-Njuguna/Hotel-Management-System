import { useState } from 'react';
import { LogOut } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { send } from '../../services/api';
import { useSession } from '../../services/session';
import { isVerificationLink } from '../../app/navigation';
import { useCommand } from './AuthFrame';

export function SignOutButton() {
  const { refresh } = useSession();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [failed, setFailed] = useState(false);
  const { pending, run } = useCommand();
  function signOut() {
    void run(async () => {
      setFailed(false);
      try {
        await send('auth/logout/', 'POST', {});
        await refresh();
        navigate('/login', { replace: true, state: { signedOut: true, ...(isVerificationLink(pathname) ? { from: pathname } : {}) } });
      } catch { setFailed(true); await refresh(); }
    });
  }
  return <div className="signout-control"><button className="rail-signout" onClick={signOut} type="button" disabled={pending}>
    <LogOut size={16} aria-hidden="true" />{pending ? 'Signing out…' : 'Sign out'}
  </button>{failed && <p role="alert">Could not confirm sign-out. Please try again.</p>}</div>;
}
