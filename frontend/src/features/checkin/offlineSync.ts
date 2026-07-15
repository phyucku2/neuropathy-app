/**
 * Offline check-in sync (ADR-0030): flush the offlineQueue to POST /adl when
 * connectivity returns. Every pass is scoped to the CURRENT authenticated owner
 * (MeOut.user_id) — another account's entries are never read, let alone posted.
 *
 * Triggered (by OfflineCheckInSync + CheckInPage) on: (a) app boot once the auth
 * restore lands (authenticated only), (b) window 'online' events, (c) after a
 * successful new online submission. The backend ACCEPTS a client-supplied
 * `check_in_date` (backend/app/schemas/ingestion.py: `check_in_date: date | None`;
 * the route uses it verbatim, rejecting only far-future dates), so every queued
 * entry is sent with the LOCAL calendar day it was captured on — honest data,
 * never re-dated to "today". Entries flush oldest day first.
 *
 * Staleness guard: the pass iterates a snapshot, so immediately before EACH POST
 * the entry is re-read from the queue and skipped if it is gone or was replaced —
 * a fresh online submission (which removes its day's queued entry) must never be
 * superseded by this pass posting the older, stale answers after it.
 *
 * Failure handling:
 * - Network error (fetch TypeError): stop — the remaining entries stay queued for
 *   the next trigger.
 * - 409/422 (feature off / rejected date): the server has refused this entry's
 *   content — retrying would loop forever, so it is DROPPED and the refusal is
 *   surfaced once via the notice buffer below.
 * - 401 (auth expired mid-flush): stop, leaving entries queued. If the expiry also
 *   cleared the session, tokenStore.clearSession has already emptied the queue —
 *   the privacy rule (queued answers never outlive the session) wins over retry.
 * - Any other status (e.g. 500): stop and retry on a later trigger.
 *
 * Single-flight with a rerun: 'online' can fire repeatedly and triggers can
 * overlap, so only one pass runs at a time — but a trigger that arrives MID-pass
 * queues exactly one FRESH pass after it (all mid-pass callers share it). The
 * in-flight pass works from a stale snapshot; the fresh pass guarantees a
 * trigger's reason (e.g. "the network clearly works now") is honored for every
 * entry, including days the stale pass already walked past.
 */

import { ApiError } from '../../api/client';
import { postAdlCheckIn } from '../../api/endpoints';
import type { AdlCheckInOut } from '../../api/types';
import { getQueuedCheckIn, listQueuedCheckIns, removeQueuedCheckIn } from './offlineQueue';
import type { QueuedCheckIn } from './offlineQueue';

export interface SyncedCheckIn {
  entry: QueuedCheckIn;
  result: AdlCheckInOut;
}

export interface DroppedCheckIn {
  entry: QueuedCheckIn;
  /** The server's refusal detail, verbatim (ApiError.detail). */
  detail: string;
}

export interface FlushOutcome {
  synced: SyncedCheckIn[];
  dropped: DroppedCheckIn[];
  /** Entries still queued after this pass (network/auth stopped the flush). */
  remaining: number;
}

type FlushListener = (outcome: FlushOutcome) => void;
const listeners = new Set<FlushListener>();

/** Dropped-entry notices not yet shown to the user — consumed exactly once. */
let unseenDropped: DroppedCheckIn[] = [];

/** True while `entry` is still the live queued entry for its day (same capture,
 * not removed and not replaced by a newer same-day capture mid-pass). */
function stillQueued(ownerId: string, entry: QueuedCheckIn): boolean {
  return getQueuedCheckIn(ownerId, entry.check_in_date)?.queued_at === entry.queued_at;
}

/** Remove `entry` only if it is still the live queued entry — a newer same-day
 * capture that replaced it mid-POST must survive to sync on a later pass. */
function removeIfStillQueued(ownerId: string, entry: QueuedCheckIn): void {
  if (stillQueued(ownerId, entry)) {
    removeQueuedCheckIn(ownerId, entry.check_in_date);
  }
}

async function runFlush(ownerId: string): Promise<FlushOutcome> {
  const synced: SyncedCheckIn[] = [];
  const dropped: DroppedCheckIn[] = [];
  for (const entry of listQueuedCheckIns(ownerId)) {
    // Re-read right before the POST: a fresh submission may have recalled this
    // entry (removeQueuedCheckIn) while an earlier entry's POST was in flight —
    // posting the stale snapshot now would supersede the fresh answers.
    if (!stillQueued(ownerId, entry)) {
      continue;
    }
    try {
      const result = await postAdlCheckIn({
        walking: entry.walking,
        stairs: entry.stairs,
        balance_confidence: entry.balance_confidence,
        check_in_date: entry.check_in_date,
        // Symptom items ride along when they were captured (ADR-0034 Phase 1); a
        // base check-in has neither and sends nothing extra.
        ...(entry.pain !== undefined ? { pain: entry.pain } : {}),
        ...(entry.numbness !== undefined ? { numbness: entry.numbness } : {}),
      });
      removeIfStillQueued(ownerId, entry);
      synced.push({ entry, result });
    } catch (cause) {
      if (cause instanceof ApiError && (cause.status === 409 || cause.status === 422)) {
        // The server refused this entry's content — drop it (a retry can never
        // succeed) and surface the refusal once. Honest data over a silent loop.
        removeIfStillQueued(ownerId, entry);
        dropped.push({ entry, detail: cause.detail });
        continue;
      }
      // Still offline, auth expired, or a transient server fault — stop here;
      // whatever is left stays queued for the next trigger.
      break;
    }
  }
  const outcome: FlushOutcome = {
    synced,
    dropped,
    remaining: listQueuedCheckIns(ownerId).length,
  };
  if (synced.length > 0 || dropped.length > 0) {
    unseenDropped = [...unseenDropped, ...dropped];
    for (const listener of listeners) {
      listener(outcome);
    }
  }
  return outcome;
}

let flushInFlight: Promise<FlushOutcome> | null = null;
let queuedRerun: Promise<FlushOutcome> | null = null;

/**
 * Flush the queue for the given owner. Single-flight: only one pass runs at a
 * time. A call while a pass is in flight queues ONE fresh pass after it (shared
 * by every mid-flight caller) and resolves with THAT pass's outcome — the
 * in-flight pass iterates a stale snapshot, so a new trigger must get a pass
 * that re-reads the queue from the top (no day is skipped, nothing stale wins).
 */
export function flushQueuedCheckIns(ownerId: string): Promise<FlushOutcome> {
  if (flushInFlight === null) {
    flushInFlight = runFlush(ownerId).finally(() => {
      flushInFlight = null;
    });
    return flushInFlight;
  }
  queuedRerun ??= flushInFlight
    .catch(() => undefined) // a failed pass must not swallow the rerun
    .then(() => {
      queuedRerun = null;
      return flushQueuedCheckIns(ownerId);
    });
  return queuedRerun;
}

/** Subscribe to flush outcomes that synced or dropped at least one entry. */
export function subscribeFlushOutcomes(listener: FlushListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * Dropped-entry notices not yet shown, consumed exactly once ("surface the detail
 * once"): the check-in page pulls this on mount and after each flush outcome.
 */
export function consumeDroppedNotices(): DroppedCheckIn[] {
  const out = unseenDropped;
  unseenDropped = [];
  return out;
}
