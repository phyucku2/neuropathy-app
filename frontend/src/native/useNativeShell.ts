/**
 * React entry point for the native shell (ADR-0025). Runs once on mount: initializes the status
 * bar / splash / hardware-back wiring and cleans the listener up on unmount. No-op on web (the
 * underlying `initNativeShell` gates on the platform), so it is safe to call unconditionally.
 */

import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { initNativeShell } from './nativeShell';

export function useNativeShell(): void {
  const navigate = useNavigate();
  useEffect(() => {
    let cancelled = false;
    let cleanup: () => void = () => undefined;
    void initNativeShell(() => navigate(-1)).then((detach) => {
      if (cancelled) {
        detach();
      } else {
        cleanup = detach;
      }
    });
    return () => {
      cancelled = true;
      cleanup();
    };
  }, [navigate]);
}
