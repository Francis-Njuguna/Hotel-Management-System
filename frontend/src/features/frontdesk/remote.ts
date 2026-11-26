import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../services/api';

export function query(stem: string, filters: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams();
  for (const [name, value] of Object.entries(filters)) {
    if (value !== '' && value !== undefined) params.set(name, String(value));
  }
  const suffix = params.toString();
  return suffix ? `${stem}?${suffix}` : stem;
}

export function messageOf(problem: unknown): string {
  if (problem instanceof Error && problem.message) return problem.message;
  return typeof problem === 'string' && problem ? problem : 'The request failed. Check your connection and try again.';
}

export function isConflict(problem: unknown): boolean {
  return typeof problem === 'object' && problem !== null && 'status' in problem && problem.status === 409;
}

export interface ReadResult<T> {
  data: T | null;
  loading: boolean;
  error: string;
  retry: () => void;
}

// Only the current path/revision can appear in the UI, even if an older lookup finishes later.
export function useRead<T>(path: string | null, decode: (value: unknown) => T, refreshKey = 0): ReadResult<T> {
  const [revision, setRevision] = useState(0);
  const [snapshot, setSnapshot] = useState<{ key: string; data: T | null; error: string } | null>(null);
  const key = JSON.stringify([path, revision, refreshKey]);
  const retry = useCallback(() => setRevision(value => value + 1), []);
  useEffect(() => {
    setSnapshot(null);
    if (!path) return;
    const request = new AbortController();
    api<unknown>(path, { signal: request.signal }).then(value => {
      if (!request.signal.aborted) setSnapshot({ key, data: decode(value), error: '' });
    }).catch((problem: unknown) => {
      if (!request.signal.aborted) setSnapshot({ key, data: null, error: messageOf(problem) });
    });
    return () => request.abort();
  }, [path, key, decode]);
  const current = path && snapshot?.key === key ? snapshot : null;
  return { data: current?.data ?? null, loading: path !== null && !current, error: current?.error ?? '', retry };
}

// No automatic mutation retry: registration and admission are not read operations.
export function useCommand() {
  const submitting = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function run<T>(operation: () => Promise<T>, success: (value: T) => void, failed?: (problem: unknown) => void) {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError('');
    try {
      const value = await operation();
      success(value);
    } catch (problem) {
      // A transport failure / malformed success body does not prove a write rolled back.
      const status = typeof problem === 'object' && problem !== null && 'status' in problem ? problem.status : null;
      setError(typeof status === 'number' && status < 500 ? messageOf(problem)
        : `${messageOf(problem)} Check the current record before resubmitting; the server may have received the change.`);
      failed?.(problem);
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  return { busy, error, setError, run };
}
