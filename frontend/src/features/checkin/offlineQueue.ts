/**
 * Offline check-in queue (ADR-0030).
 *
 * When POST /adl fails with a NETWORK error (offline), the three 0-4 answers are
 * captured here and synced by offlineSync.ts when connectivity returns. Storage is
 * `localStorage` — deliberately durable across tab/app restarts, because an offline
 * patient may close the app before connectivity returns. Privacy posture (reviewed,
 * ADR-0030): the payload is three low-sensitivity ordinal self-ratings + a date, on
 * the patient's own device (Android manifest sets allowBackup=false; web storage is
 * browser-profile-local), held only until sync, and cleared on EVERY session clear —
 * logout, account deletion, and expiry all funnel through tokenStore.clearSession,
 * which calls `clearQueuedCheckIns()`. Never tokens, never free text.
 *
 * Supersede semantics mirror the server (ADR-0006): at most ONE pending check-in per
 * calendar date — a newer same-day capture REPLACES the queued one, exactly as the
 * server's revises_id chain would keep only the newest same-day submission current.
 *
 * Pure module: no React, no API imports (tokenStore imports this — keep it leaf-level).
 * The clock is injectable for tests.
 */

export const OFFLINE_CHECKIN_QUEUE_KEY = 'neuropathy.offline_checkins';

export interface QueuedCheckIn {
  walking: number;
  stairs: number;
  balance_confidence: number;
  /** The patient's LOCAL calendar day at capture time (YYYY-MM-DD) — never UTC. */
  check_in_date: string;
  /** When the entry was captured (ISO instant) — provenance for the sync notice. */
  queued_at: string;
}

const DATE_SHAPE = /^\d{4}-\d{2}-\d{2}$/;

function isAnswer(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= 4;
}

function isQueuedCheckIn(value: unknown): value is QueuedCheckIn {
  if (value === null || typeof value !== 'object') {
    return false;
  }
  const entry = value as Record<string, unknown>;
  return (
    isAnswer(entry['walking']) &&
    isAnswer(entry['stairs']) &&
    isAnswer(entry['balance_confidence']) &&
    typeof entry['check_in_date'] === 'string' &&
    DATE_SHAPE.test(entry['check_in_date']) &&
    typeof entry['queued_at'] === 'string'
  );
}

/**
 * All queued entries, oldest calendar day first (the flush order). Corrupt or
 * unreadable storage reads as an empty queue — never a throw into the UI.
 */
export function listQueuedCheckIns(): QueuedCheckIn[] {
  try {
    const raw = localStorage.getItem(OFFLINE_CHECKIN_QUEUE_KEY);
    if (raw === null) {
      return [];
    }
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed
      .filter(isQueuedCheckIn)
      .sort((a, b) => a.check_in_date.localeCompare(b.check_in_date));
  } catch {
    // Corrupt JSON or storage unavailable — an empty queue, not a crash.
    return [];
  }
}

export function getQueuedCheckIn(checkInDate: string): QueuedCheckIn | null {
  return listQueuedCheckIns().find((entry) => entry.check_in_date === checkInDate) ?? null;
}

function write(entries: QueuedCheckIn[]): boolean {
  try {
    if (entries.length === 0) {
      localStorage.removeItem(OFFLINE_CHECKIN_QUEUE_KEY);
    } else {
      localStorage.setItem(OFFLINE_CHECKIN_QUEUE_KEY, JSON.stringify(entries));
    }
    return true;
  } catch {
    // Storage unavailable/full — the caller falls back to its normal error path.
    return false;
  }
}

/**
 * Capture a check-in for later sync. At most one entry per calendar date: a newer
 * same-day capture REPLACES the queued one (ADR-0006 supersede semantics — the
 * newest answers for a day are the ones that count). Returns the stored entry, or
 * null when storage is unavailable (the caller then shows its normal error).
 */
export function enqueueCheckIn(
  input: Omit<QueuedCheckIn, 'queued_at'>,
  now: () => Date = () => new Date(),
): QueuedCheckIn | null {
  const entry: QueuedCheckIn = { ...input, queued_at: now().toISOString() };
  const others = listQueuedCheckIns().filter((e) => e.check_in_date !== entry.check_in_date);
  return write([...others, entry]) ? entry : null;
}

/** Remove one day's entry (after a successful sync, or when a newer online
 * submission for the same day superseded it). */
export function removeQueuedCheckIn(checkInDate: string): void {
  write(listQueuedCheckIns().filter((entry) => entry.check_in_date !== checkInDate));
}

/**
 * Drop everything. Wired into tokenStore.clearSession (the SHARED session-clear
 * path — logout, account deletion, session expiry), so queued health answers never
 * outlive the session that captured them (ADR-0030 privacy posture).
 */
export function clearQueuedCheckIns(): void {
  try {
    localStorage.removeItem(OFFLINE_CHECKIN_QUEUE_KEY);
  } catch {
    // Storage unavailable — nothing was persisted there to clear.
  }
}
