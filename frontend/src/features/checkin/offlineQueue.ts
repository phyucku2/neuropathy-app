/**
 * Offline check-in queue (ADR-0030).
 *
 * When POST /adl fails with a NETWORK error (offline), the three 0-4 answers are
 * captured here and synced by offlineSync.ts when connectivity returns. Storage is
 * `localStorage` — deliberately durable across tab/app restarts, because an offline
 * patient may close the app before connectivity returns. That durability means the
 * queue CAN outlive a tab that was closed without logging out; the retention is
 * bounded by four rules (privacy posture, reviewed — ADR-0030):
 *  1. Entries are BOUND to the account that captured them: the store is keyed by
 *     the owner's user id, and every read/write takes the current owner — one
 *     account can never see or flush another account's answers.
 *  2. When a (possibly different) user signs in, every OTHER owner's entries are
 *     purged (`purgeQueuedCheckInsForOtherOwners`) — foreign health answers do not
 *     persist once we know a different user is active on this browser.
 *  3. Entries older than QUEUED_CHECKIN_MAX_AGE_DAYS are dropped by a TTL sweep at
 *     module load — a weeks-old flush would be clinically stale.
 *  4. The whole queue is cleared on every REAL session end — logout, account
 *     deletion, and a genuine auth rejection all funnel through
 *     tokenStore.clearSession, which calls `clearQueuedCheckIns()`. (An offline
 *     boot is NOT a session end and leaves the queue intact — see AuthContext.)
 * The payload is three low-sensitivity ordinal self-ratings + a date, on the
 * patient's own device (Android manifest sets allowBackup=false; web storage is
 * browser-profile-local). Never tokens, never free text.
 *
 * Supersede semantics mirror the server (ADR-0006): at most ONE pending check-in per
 * calendar date per owner — a newer same-day capture REPLACES the queued one, exactly
 * as the server's revises_id chain would keep only the newest same-day submission
 * current.
 *
 * Pure module: no React, no API imports (tokenStore imports this — keep it leaf-level).
 * The clock is injectable for tests.
 */

export const OFFLINE_CHECKIN_QUEUE_KEY = 'neuropathy.offline_checkins';

/**
 * TTL for queued entries: a check-in that has waited this long is clinically stale —
 * flushing it would pollute the trend more than losing it, so the module-load sweep
 * (`purgeExpiredQueuedCheckIns`) drops anything older.
 */
export const QUEUED_CHECKIN_MAX_AGE_DAYS = 14;

export interface QueuedCheckIn {
  walking: number;
  stairs: number;
  balance_confidence: number;
  /** Symptom items (ADR-0034 Phase 1): 0-10 pain + numbness, present only when the
   *  symptom-capture toggle was on at capture time. Higher = worse. Optional so a
   *  base (function-only) check-in queues unchanged. */
  pain?: number;
  numbness?: number;
  /** The patient's LOCAL calendar day at capture time (YYYY-MM-DD) — never UTC. */
  check_in_date: string;
  /** When the entry was captured (ISO instant) — provenance for the sync notice. */
  queued_at: string;
}

/** Entries keyed by the owning account's user id (MeOut.user_id). */
type QueueStore = Record<string, QueuedCheckIn[]>;

const DATE_SHAPE = /^\d{4}-\d{2}-\d{2}$/;

function isAnswer(value: unknown): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= 4;
}

/** A 0-10 symptom item (pain/numbness). Absent (undefined) is valid — the item is
 *  optional; anything present must be an integer in range. */
function isSymptom(value: unknown): value is number | undefined {
  return (
    value === undefined ||
    (typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= 10)
  );
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
    isSymptom(entry['pain']) &&
    isSymptom(entry['numbness']) &&
    typeof entry['check_in_date'] === 'string' &&
    DATE_SHAPE.test(entry['check_in_date']) &&
    typeof entry['queued_at'] === 'string'
  );
}

/**
 * The whole per-owner store. Corrupt or unreadable storage reads as empty — never a
 * throw into the UI. The pre-user-binding array format also reads as empty: those
 * entries cannot be attributed to an owner, so they are dropped rather than risked
 * against the wrong record (privacy over recovery).
 */
function readStore(): QueueStore {
  try {
    const raw = localStorage.getItem(OFFLINE_CHECKIN_QUEUE_KEY);
    if (raw === null) {
      return {};
    }
    const parsed: unknown = JSON.parse(raw);
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return {};
    }
    const store: QueueStore = {};
    for (const [ownerId, value] of Object.entries(parsed)) {
      if (Array.isArray(value)) {
        const entries = (value as unknown[]).filter(isQueuedCheckIn);
        if (entries.length > 0) {
          store[ownerId] = entries;
        }
      }
    }
    return store;
  } catch {
    // Corrupt JSON or storage unavailable — an empty queue, not a crash.
    return {};
  }
}

function writeStore(store: QueueStore): boolean {
  try {
    const compact: QueueStore = {};
    for (const [ownerId, entries] of Object.entries(store)) {
      if (entries.length > 0) {
        compact[ownerId] = entries;
      }
    }
    if (Object.keys(compact).length === 0) {
      localStorage.removeItem(OFFLINE_CHECKIN_QUEUE_KEY);
    } else {
      localStorage.setItem(OFFLINE_CHECKIN_QUEUE_KEY, JSON.stringify(compact));
    }
    return true;
  } catch {
    // Storage unavailable/full — the caller falls back to its normal error path.
    return false;
  }
}

/**
 * The given owner's queued entries, oldest calendar day first (the flush order).
 * Other owners' entries are invisible here — the queue is per-account.
 */
export function listQueuedCheckIns(ownerId: string): QueuedCheckIn[] {
  return (readStore()[ownerId] ?? []).sort((a, b) =>
    a.check_in_date.localeCompare(b.check_in_date),
  );
}

export function getQueuedCheckIn(ownerId: string, checkInDate: string): QueuedCheckIn | null {
  return listQueuedCheckIns(ownerId).find((entry) => entry.check_in_date === checkInDate) ?? null;
}

/**
 * Capture a check-in for later sync, bound to the capturing account. At most one
 * entry per calendar date per owner: a newer same-day capture REPLACES the queued
 * one (ADR-0006 supersede semantics — the newest answers for a day are the ones
 * that count). Returns the stored entry, or null when storage is unavailable (the
 * caller then shows its normal error).
 */
export function enqueueCheckIn(
  ownerId: string,
  input: Omit<QueuedCheckIn, 'queued_at'>,
  now: () => Date = () => new Date(),
): QueuedCheckIn | null {
  const entry: QueuedCheckIn = { ...input, queued_at: now().toISOString() };
  const store = readStore();
  const others = (store[ownerId] ?? []).filter((e) => e.check_in_date !== entry.check_in_date);
  store[ownerId] = [...others, entry];
  return writeStore(store) ? entry : null;
}

/** Remove one day's entry for one owner (after a successful sync, or when a newer
 * online submission for the same day superseded it). */
export function removeQueuedCheckIn(ownerId: string, checkInDate: string): void {
  const store = readStore();
  store[ownerId] = (store[ownerId] ?? []).filter((entry) => entry.check_in_date !== checkInDate);
  writeStore(store);
}

/**
 * Drop everything, all owners. Wired into tokenStore.clearSession (the SHARED
 * session-clear path — logout, account deletion, a genuine auth rejection), so
 * queued health answers never outlive a REAL session end (ADR-0030 privacy
 * posture). A transient offline failure never calls this — see AuthContext.
 */
export function clearQueuedCheckIns(): void {
  try {
    localStorage.removeItem(OFFLINE_CHECKIN_QUEUE_KEY);
  } catch {
    // Storage unavailable — nothing was persisted there to clear.
  }
}

/**
 * Purge every OTHER owner's entries, keeping only the given owner's. Called the
 * moment an authenticated profile is confirmed (login/register/session restore):
 * on a shared browser, another account's captured health answers are foreign PHI
 * and must not persist once we know a different user is active (ADR-0030).
 */
export function purgeQueuedCheckInsForOtherOwners(ownerId: string): void {
  const store = readStore();
  const own = store[ownerId];
  writeStore(own === undefined ? {} : { [ownerId]: own });
}

/**
 * TTL sweep (run at module load, i.e. every app boot): drop entries queued more
 * than QUEUED_CHECKIN_MAX_AGE_DAYS ago, for every owner. Entries whose queued_at
 * does not parse are dropped too — they could otherwise never expire.
 */
export function purgeExpiredQueuedCheckIns(now: () => Date = () => new Date()): void {
  const cutoff = now().getTime() - QUEUED_CHECKIN_MAX_AGE_DAYS * 24 * 60 * 60 * 1000;
  const store = readStore();
  const fresh: QueueStore = {};
  for (const [ownerId, entries] of Object.entries(store)) {
    fresh[ownerId] = entries.filter((entry) => {
      const queuedAt = Date.parse(entry.queued_at);
      return Number.isFinite(queuedAt) && queuedAt >= cutoff;
    });
  }
  writeStore(fresh);
}

// Bound retention rule 3: stale entries do not survive an app boot.
purgeExpiredQueuedCheckIns();
