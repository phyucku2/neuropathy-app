/**
 * Invisible sync trigger for the offline check-in queue (ADR-0030). Mounted inside
 * the authenticated patient area (App.tsx), it:
 *  - flushes once when the authenticated session is up (app boot after restore),
 *  - flushes on every window 'online' event while the session lasts.
 * The third trigger — after a successful new submission — lives in CheckInPage.
 *
 * Renders nothing; anonymous/restoring sessions never register the listener, so no
 * unauthenticated POST is ever attempted.
 */

import { useEffect } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { flushQueuedCheckIns } from './offlineSync';

export function OfflineCheckInSync() {
  const { status } = useAuth();

  useEffect(() => {
    if (status !== 'authenticated') {
      return;
    }
    void flushQueuedCheckIns();
    const onOnline = () => {
      void flushQueuedCheckIns();
    };
    window.addEventListener('online', onOnline);
    return () => {
      window.removeEventListener('online', onOnline);
    };
  }, [status]);

  return null;
}
