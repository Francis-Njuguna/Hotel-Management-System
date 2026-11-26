import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Eye, EyeOff, KeyRound, MapPin, ShieldCheck, type LucideIcon } from 'lucide-react';
import { Brand, HotelFacade } from '../../app/Identity';

export function AuthFrame({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  useEffect(() => { document.title = `${title} · Hotel A Front Office`; }, [title]);
  return <main className="auth-layout" id="main-content">
    <aside className="auth-story" aria-label="Hotel A staff workspace">
      <Brand />
      <div className="auth-story-copy"><div className="auth-kicker"><span /> Property workspace</div>
        <h2>Front Office<span>.</span></h2><p>The staff workspace for reservations, rooms and daily service at Hotel A.</p>
      </div>
      <HotelFacade />
      <div className="auth-property"><span><MapPin size={15} aria-hidden="true" /> Property time</span><strong>Africa/Nairobi · EAT</strong></div>
    </aside>
    <section className="auth-form-side" aria-labelledby="auth-title"><div className="auth-form-content">
      <div className="auth-icon"><KeyRound size={24} aria-hidden="true" /></div>
      <span className="eyebrow">Staff workspace</span><h1 id="auth-title">{title}</h1><p className="auth-intro">{description}</p>
      {children}
      <div className="auth-footnote"><ShieldCheck size={16} aria-hidden="true" /> For authorized Hotel A staff only.</div>
    </div></section>
  </main>;
}

export function AuthResult({ icon: Icon, title, children }: { icon: LucideIcon; title: string; children: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);
  return <div className="auth-result" role="status" ref={ref} tabIndex={-1}><Icon size={26} aria-hidden="true" /><strong>{title}</strong><p>{children}</p></div>;
}

type SecretProps = {
  id: string; label: string; value: string; change: (value: string) => void;
  completion: 'current-password' | 'new-password'; error?: string;
};

export function SecretField({ id, label, value, change, completion, error }: SecretProps) {
  const [visible, setVisible] = useState(false);
  return <div className="field"><label htmlFor={id}>{label}</label>
    <div className="secret-input"><input id={id} name={id} type={visible ? 'text' : 'password'} autoComplete={completion} required
      value={value} onChange={(event) => change(event.target.value)} aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-error` : undefined} />
      <button type="button" aria-label={`${visible ? 'Hide' : 'Show'} ${label.toLowerCase()}`} aria-controls={id}
        onClick={() => setVisible(!visible)}>{visible ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}</button>
    </div>{error && <span role="alert" id={`${id}-error`} className="field-error">{error}</span>}
  </div>;
}

/** Synchronous lock also covers two submissions within the same render. */
export function useCommand() {
  const lock = useRef(false);
  const mounted = useRef(true);
  const [pending, setPending] = useState(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  async function run(action: () => Promise<void>) {
    if (lock.current) return;
    lock.current = true;
    setPending(true);
    try { await action(); } finally { lock.current = false; if (mounted.current) setPending(false); }
  }
  return { pending, run };
}

export function httpStatus(error: unknown): number | undefined {
  if (error && typeof error === 'object' && 'status' in error && typeof error.status === 'number') return error.status;
  return undefined;
}
