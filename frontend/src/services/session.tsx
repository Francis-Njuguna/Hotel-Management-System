import { createContext, useCallback, useContext, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { api, bindOperator, type SessionUser } from './api';
export { can, type SessionUser } from './api';

type Session = { user: SessionUser | null; loading: boolean; error: string | null };
const checking: Session = { user: null, loading: true, error: null };
const signedOut: Session = { user: null, loading: false, error: null };
const Context = createContext<(Session & { refresh: () => Promise<void> }) | undefined>(undefined);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState(checking);
  const mounted = useRef(false);
  const pending = useRef<AbortController | null>(null);
  const operatorId = session.user?.id ?? null;

  // Bind writes to the committed view, not to a network callback ahead of its render.
  useLayoutEffect(() => {
    bindOperator(operatorId);
    return () => bindOperator(null);
  }, [operatorId]);

  const refresh = useCallback(async () => {
    if (!mounted.current) return;
    pending.current?.abort();
    const read = new AbortController();
    pending.current = read;

    let next: Session;
    try {
      const { user } = await api<{ user: SessionUser | null }>('auth/me/', { signal: read.signal });
      next = { user, loading: false, error: null };
    } catch (cause) {
      next = { ...signedOut, error: cause instanceof Error && cause.message ? cause.message : 'Session service unavailable.' };
    }
    // A superseded read may already have a response queued when aborted. Neither
    // its success nor its failure may settle a different admission check.
    if (pending.current !== read) return;
    pending.current = null;
    setSession(next);
  }, []);

  useLayoutEffect(() => {
    mounted.current = true;
    const cancelRead = () => {
      pending.current?.abort();
      pending.current = null;
    };
    const expired = () => { cancelRead(); setSession(signedOut); };
    const reload = () => { void refresh(); };
    // A known identity change gates the old workspace until verified. A routine
    // focus check does not unmount an admitted view or discard its drafts.
    const operatorChanged = () => { setSession(checking); reload(); };
    const storageChanged = (event: StorageEvent) => {
      if (event.key === 'hotel-a:session-change') operatorChanged();
    };

    window.addEventListener('hms:session-expired', expired);
    window.addEventListener('hms:operator-changed', operatorChanged);
    window.addEventListener('focus', reload);
    window.addEventListener('storage', storageChanged);
    reload();
    return () => {
      mounted.current = false;
      cancelRead();
      window.removeEventListener('hms:session-expired', expired);
      window.removeEventListener('hms:operator-changed', operatorChanged);
      window.removeEventListener('focus', reload);
      window.removeEventListener('storage', storageChanged);
    };
  }, [refresh]);

  return <Context.Provider key={operatorId ?? 'signed-out'} value={{ ...session, refresh }}>{children}</Context.Provider>;
}

export function useSession() {
  const ctx = useContext(Context);
  if (!ctx) throw new Error('SessionProvider is required');
  return ctx;
}
