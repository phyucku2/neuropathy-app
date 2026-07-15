/**
 * Offline check-in sync (ADR-0030): flush the offlineQueue to POST /adl when
 * connectivity returns.
 *
 * Triggered (by OfflineCheckInSync + CheckInPage) on: (a) app boot once the auth
 * restore lands (authenticated only), (b) window 'online' events, (c) after a
 * successful new online submission. The backend ACCEPTS a client-supplied
 * `check_in_date` (backend/app/schemas/ingestion.py: `check_in_date: date | None`;
 * the route uses it verbatim, rejecting only far-future dates), so every queued
 * entry is sent with the LOCAL calendar date it was captured on — honest data,
 * never re-dated to "today". Entries flush oldest day first.
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
 * Single-flight: 'online' can fire repeatedly and triggers can overlap; concurrent
 * calls share one flush pass.
 */

import { ApiError } from '../../api/client';
import { postAdlCheckIn } from '../../api/endpoints';
import type { AdlCheckInOut } from '../../api/types';
import { listQueuedCheckIns, removeQueuedCheckIn, type QueuedCheckIn } from './offlineQueue';

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

let flushInFlight: Promise<FlushOutcome> | null = null;

async function runFlush(): Promise<FlushOutcome> {
  const synced: SyncedCheckIn[] = [];
  const dropped: DroppedCheckIn[] = [];
  for (const entry of listQueuedCheckIns()) {
    try {
      const result = await postAdlCheckIn({
        walking: entry.walking,
        stairs: entry.stairs,
        balance_confidence: entry.balance_confidence,
        check_in_date: entry.check_in_date,
      });
      removeQueuedCheckIn(entry.check_in_date);
      synced.push({ entry, result });
    } catch (cause) {
      if (cause instanceof ApiError && (cause.status === 409 || cause.status === 422)) {
        // The server refused this entry's content — drop it (a retry can never
        // succeed) and surface the refusal once. Honest data over a silent loop.
        removeQueuedCheckIn(entry.check_in_date);
        dropped.push({ entry, detail: cause.detail });
        continue;
      }
      // Still offline, auth expired, or a transient server fault — stop here;
      // whatever is left stays queued for the next trigger.
      break;
    }
  }
  const outcome: FlushOutcome = { synced, dropped, remaining: listQueuedCheckIns().length };
  if (synced.length > 0 || dropped.length > 0) {
    unseenDropped = [...unseenDropped, ...dropped];
    for (const listener of listeners) {
      listener(outcome);
    }
  }
  return outcome;
}

/** Flush the queue — single-flight (concurrent triggers share one pass). */
export function flushQueuedCheckIns(): Promise<FlushOutcome> {
  flushInFlight ??= runFlush().finally(() => {
    flushInFlight = null;
  });
  return flushInFlight;
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
