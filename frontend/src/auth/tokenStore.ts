/**
 * Token handling (security-critical — ADR-0015):
 *
 * - The ACCESS token lives in memory only (this module's closure). It is never
 *   written to storage, never logged, and dies with the tab.
 * - The REFRESH token lives in sessionStorage: tab-scoped, cleared when the tab
 *   closes, survives an in-tab reload. The XSS tradeoff is documented in
 *   ADR-0015 (httpOnly cookies were rejected: the API has no cookie/CSRF surface).
 *
 * Session-expiry listeners let the auth context react when a refresh fails
 * without the API client importing React.
 */

const REFRESH_TOKEN_KEY = 'neuropathy.refresh_token';

let accessToken: string | null = null;

type SessionExpiredListener = () => void;
const sessionExpiredListeners = new Set<SessionExpiredListener>();

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string): void {
  accessToken = token;
}

export function getRefreshToken(): string | null {
  return sessionStorage.getItem(REFRESH_TOKEN_KEY);
}

export function storeSession(tokens: { access_token: string; refresh_token: string }): void {
  accessToken = tokens.access_token;
  sessionStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
}

export function clearSession(): void {
  accessToken = null;
  sessionStorage.removeItem(REFRESH_TOKEN_KEY);
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
