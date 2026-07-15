/**
 * Token handling (security-critical — ADR-0015, extended for native by ADR-0024):
 *
 * - The ACCESS token lives in memory only (this module's closure). It is never
 *   written to storage, never logged, and dies with the tab/process. Unchanged on
 *   every platform.
 * - The REFRESH token lives in a platform-selected DURABLE store (refreshTokenBackend):
 *   `sessionStorage` on web (tab-scoped, the ADR-0015 XSS tradeoff, documented there),
 *   the Keystore-backed secure store on native. `getRefreshToken()` stays a synchronous
 *   read; on native the value is primed from the Keystore by `primeRefreshToken()` during
 *   the restore flow before any refresh is attempted.
 *
 * Session-expiry listeners let the auth context react when a refresh fails
 * without the API client importing React.
 */

import { clearQueuedCheckIns } from '../features/checkin/offlineQueue';
import { refreshTokenBackend } from './refreshTokenBackend';

let accessToken: string | null = null;

type SessionExpiredListener = () => void;
const sessionExpiredListeners = new Set<SessionExpiredListener>();

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string): void {
  accessToken = token;
}

/** Synchronous best-effort read (web: live sessionStorage; native: mirror primed by
 * `primeRefreshToken()`). */
export function getRefreshToken(): string | null {
  return refreshTokenBackend.peek();
}

/** Load the durable refresh token into the synchronously-readable layer. On web this just
 * reads sessionStorage; on native it primes the in-memory mirror from the Keystore so the
 * subsequent refresh-on-401 can read it synchronously. Returns the token (or null). */
export async function primeRefreshToken(): Promise<string | null> {
  return refreshTokenBackend.load();
}

export async function storeSession(tokens: {
  access_token: string;
  refresh_token: string;
}): Promise<void> {
  accessToken = tokens.access_token;
  await refreshTokenBackend.save(tokens.refresh_token);
}

export function clearSession(): void {
  accessToken = null;
  refreshTokenBackend.clear();
  // Queued offline check-ins are health answers persisted only until sync
  // (ADR-0030): they must never outlive a REAL session end. This is the SHARED
  // clear path — logout, account deletion (DeleteAccountCard → logout()), and a
  // genuine auth rejection (notifySessionExpired) all funnel through here, so
  // the queue-clear lives here rather than in any UI flow. Transient NETWORK
  // failures (an offline boot, a network-failed refresh) deliberately never call
  // clearSession — see AuthContext + api/client — so an offline capture survives
  // until it can sync. (offlineQueue is a leaf module — no import cycle.)
  clearQueuedCheckIns();
}

export function onSessionExpired(listener: SessionExpiredListener): () => void {
  sessionExpiredListeners.add(listener);
  return () => {
    sessionExpiredListeners.delete(listener);
  };
}

export function notifySessionExpired(): void {
  clearSession();
  for (const listener of sessionExpiredListeners) {
    listener();
  }
}
