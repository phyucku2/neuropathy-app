/**
 * The pending EMR handshake (ADR-0028): POST /emr/connect returns a `state` that the
 * EMR must echo back on the redirect, and the /emr/callback relay route must verify
 * that echo against something the APP persisted — otherwise a forged callback URL
 * could relay an attacker-chosen code+state pair.
 *
 * Storage is `sessionStorage`, keyed with the token store's `neuropathy.*` naming:
 * tab-scoped like the web refresh token (the redirect round-trip to the EMR and back
 * happens in the SAME tab, so the value survives exactly as long as it needs to), and
 * it carries no secret — the `state` is a one-time CSRF correlation value the EMR sees
 * anyway, never a token.
 */

export const EMR_PENDING_CONNECT_KEY = 'neuropathy.emr_pending_connect';

export interface PendingEmrConnect {
  /** The OAuth `state` from POST /emr/connect — must match the callback's query. */
  state: string;
  connectionId: string;
  /** Display name shown while the callback relay works. */
  providerName: string;
}

export function savePendingConnect(pending: PendingEmrConnect): void {
  sessionStorage.setItem(EMR_PENDING_CONNECT_KEY, JSON.stringify(pending));
}

export function loadPendingConnect(): PendingEmrConnect | null {
  const raw = sessionStorage.getItem(EMR_PENDING_CONNECT_KEY);
  if (raw === null) {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(raw);
    if (
      parsed !== null &&
      typeof parsed === 'object' &&
      typeof (parsed as PendingEmrConnect).state === 'string' &&
      typeof (parsed as PendingEmrConnect).connectionId === 'string' &&
      typeof (parsed as PendingEmrConnect).providerName === 'string'
    ) {
      return parsed as PendingEmrConnect;
    }
  } catch {
    // Corrupt entry — treat as "no pending handshake"; the user retries from Sources.
  }
  return null;
}

export function clearPendingConnect(): void {
  sessionStorage.removeItem(EMR_PENDING_CONNECT_KEY);
}
