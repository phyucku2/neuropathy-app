/** Tiny data-fetching hook: loading / error / data + reload, no cache layer. */

import { useCallback, useEffect, useState } from 'react';
import { ApiError, messageFor } from '../api/client';

export interface ApiState<T> {
  data: T | null;
  error: string | null;
  /** HTTP status when the failure was an ApiError (e.g. 404 → neutral not-found UX). */
  errorStatus: number | null;
  loading: boolean;
  reload: () => void;
}

export function useApi<T>(fetcher: () => Promise<T>): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorStatus, setErrorStatus] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setErrorStatus(null);
    fetcher()
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setLoading(false);
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(messageFor(cause));
          setErrorStatus(cause instanceof ApiError ? cause.status : null);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [fetcher, tick]);

  const reload = useCallback(() => {
    setTick((current) => current + 1);
  }, []);

  return { data, error, errorStatus, loading, reload };
}
