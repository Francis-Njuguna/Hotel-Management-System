import { useCallback, useEffect, useState } from 'react';
import { api } from '../services/api';

type Snapshot<T> = { path: string; revision: number } & (
  { state: 'ready'; value: T } | { state: 'failed' }
);

/** Never display the previous user's, page's, or filter's rows as a new result. */
export function useResource<T>(path: string, decode?: (input: unknown) => T) {
  const [revision, setRevision] = useState(0);
  const [snapshot, setSnapshot] = useState<Snapshot<T> | null>(null);
  const reload = useCallback(() => setRevision((current) => current + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    async function load() {
      try {
        const raw = await api<T>(path, { signal: controller.signal });
        const value = decode ? decode(raw) : raw;
        if (current) setSnapshot({ path, revision, state: 'ready', value });
      } catch {
        if (current) setSnapshot({ path, revision, state: 'failed' });
      }
    }
    void load();
    return () => { current = false; controller.abort(); };
  }, [path, revision, decode]);
  const current = snapshot?.path === path && snapshot.revision === revision ? snapshot : null;
  return {
    loading: !current,
    failed: current?.state === 'failed',
    data: current?.state === 'ready' ? current.value : undefined,
    reload,
    refreshed: revision > 0 && current?.state === 'ready',
  };
}
