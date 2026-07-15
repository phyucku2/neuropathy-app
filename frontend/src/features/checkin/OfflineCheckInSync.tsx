/**
 * Invisible sync trigger for the offline check-in queue (ADR-0030). Mounted inside
 * the authenticated patient area (App.tsx), it:
 *  - flushes once when the authenticated session is up (app boot after restore),
 *  - flushes on every window 'online' event while the session lasts.
 * The third trigger — after a successful new submission — lives in CheckInPage.
 *
 * Every flush is scoped to the signed-in account's user id: only that owner's
 * queued entries are read and posted (ADR-0030 per-user binding).
 *
 * Renders nothing; anonymous/restoring sessions never register the listener, so no
 * unauthenticated POST is ever attempted.
 */

import { useEffect } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { flushQueuedCheckIns } from './offlineSync';

export function OfflineCheckInSync() {
  const { status, user } = useAuth();
  const ownerId = status === 'authenticated' && user !== null ? user.user_id : null;

  useEffect(() => {
    if (ownerId === null) {
      return;
    }
    void flushQueuedCheckIns(ownerId);
    const onOnline = () => {
      void flushQueuedCheckIns(ownerId);
    };
    window.addEventListener('online', onOnline);
    return () => {
      window.removeEventListener('online', onOnline);
    };
  }, [ownerId]);

  return null;
}
