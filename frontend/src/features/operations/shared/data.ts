import { useEffect, useRef, useState } from 'react';
import { api, type Page } from '../../../services/api';

export type Filters = Record<string, string | number | boolean | undefined>;

export function queryString(filters: Filters): string {
  const params = new URLSearchParams();
  for (const key of Object.keys(filters).sort()) {
    const value = filters[key];
    if (value !== '' && value !== undefined) params.set(key, String(value));
  }
  return params.toString();
}

export function errorText(error: unknown): string {
  return error instanceof Error && error.message.trim()
    ? error.message
    : 'The request could not be completed. Check your connection and try again.';
}

export interface Collection<T> {
  data: Page<T> | null;
  loading: boolean;
  error: string;
  page: number;
  size: number;
  go: (page: number) => void;
  retry: () => void;
}

/** Page only through our versioned API path; never request a server-supplied next URL. */
export function useCollection<T>(
  path: string, filters: Filters = {}, revision = 0, size = 12,
): Collection<T> {
  const base = queryString(filters);
  const scope = `${path}?${base}`;
  const [cursor, setCursor] = useState({ scope, page: 1 });
  const page = cursor.scope === scope ? cursor.page : 1;
  useEffect(() => {
    setCursor((old) => old.scope === scope ? old : { scope, page: 1 });
  }, [scope]);
  const [attempt, setAttempt] = useState(0);
  const url = `${scope}${base ? '&' : ''}page=${page}&page_size=${size}`;
  const key = `${url}|${revision}|${attempt}`;
  const [response, setResponse] = useState<{ key: string; data: Page<T> | null; error: string } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    api<Page<T>>(url, { signal: controller.signal }).then(
      (data) => {
        if (!current) return;
        if (!data || !Array.isArray(data.results) || typeof data.count !== 'number') {
          setResponse({ key, data: null, error: 'The server did not return a paginated list. Try reloading.' });
        } else {
          setResponse({ key, data, error: '' });
        }
      },
      (error: unknown) => { if (current) setResponse({ key, data: null, error: errorText(error) }); },
    );
    return () => { current = false; controller.abort(); };
  }, [url, key]);

  // Do not display a previous filter's records while a different page is loading.
  const result = response?.key === key ? response : null;
  return {
    data: result?.data ?? null, error: result?.error ?? '', loading: result === null,
    page, size, go: (next) => setCursor({ scope, page: Math.max(1, next) }),
    retry: () => setAttempt((value) => value + 1),
  };
}

export function useMutation() {
  const lock = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const run = async <T,>(job: () => Promise<T>, done: (value: T) => void) => {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError('');
    try {
      done(await job());
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  return { busy, error, run, fail: setError };
}

export function useWorkspace() {
  const [revision, setRevision] = useState(0);
  const [notice, setNotice] = useState('');
  return {
    revision, notice,
    clearNotice: () => setNotice(''),
    changed: (message: string) => {
      setNotice(message);
      setRevision((r) => r + 1);
    },
  };
}
