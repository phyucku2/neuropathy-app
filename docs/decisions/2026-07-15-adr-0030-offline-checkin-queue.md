# ADR-0030: Offline Check-in Queue — capture locally, sync when connectivity returns

**Date:** 2026-07-15
**Status:** Accepted
**Builds on:** ADR-0006 (same-day supersede semantics), ADR-0015 (client patterns,
verbatim API-error handling), ADR-0022 (browser E2E + console-gate discipline),
ADR-0023/0024 (native shell; allowBackup=false; session-clear paths), ADR-0027
(account deletion → logout → clearSession).

## Context

A patient submitting the daily ADL check-in while offline got a generic error and a
lost entry — the worst outcome for the product's core data stream (three 0-4 answers a
day, ADR-0006). Mobile use makes transient offline normal. The fix must not disturb
the existing verbatim handling of real API errors (409 feature-off, 422 validation,
ADR-0013/0015), must respect the one-check-in-per-day supersede model, and must not
turn into a fabricated-data path.

## Decision

### 1. Queue store: localStorage, one entry per calendar day

`frontend/src/features/checkin/offlineQueue.ts` — a pure leaf module (no React/API
imports, injectable clock). Entries carry `{walking, stairs, balance_confidence,
check_in_date, queued_at}`, where `check_in_date` is the patient's **local** calendar
day at capture time (same rule as the online path — never UTC). At most **one entry
per date**: a newer same-day capture REPLACES the queued one, mirroring the server's
supersede rule (ADR-0006: only the newest same-day check-in counts) on-device.
Corrupt/unavailable storage reads as an empty queue; failed writes return null and the
page falls back to its normal error path.

**Privacy review point — health answers persisted until sync (accepted):**

- The data is three low-sensitivity ordinal self-ratings plus a date — no free text,
  no identifiers, no tokens.
- The device is the patient's own: on Android the manifest sets `allowBackup=false`
  (ADR-0023), so the value never reaches cloud backup; on web, localStorage is
  browser-profile-local to the origin.
- Retention is bounded: entries are deleted the moment they sync, and the whole queue
  is cleared on **every session clear**. The clear is wired into the SHARED path —
  `tokenStore.clearSession()` calls `clearQueuedCheckIns()` — not into any UI flow, so
  logout, **account deletion** (DeleteAccountCard → `logout()` → `clearSession`,
  ADR-0027), failed sign-in cleanup, and session expiry (`notifySessionExpired`) all
  clear it without each flow having to remember to. (Unit-tested through the real
  deletion flow.)
- `sessionStorage` (the ADR-0015 refresh-token choice) was rejected here because it
  dies with the tab: an offline patient closing the app is the expected case, and the
  entry must survive to sync later. The larger persistence window is exactly the
  feature, bounded by the clearance rules above.

### 2. Submission flow: network failures queue; API errors keep their handling

`CheckInPage` distinguishes a **network** failure (fetch rejects with `TypeError` —
the request never reached the server) from an **API** error (`ApiError`, any 4xx/5xx —
the server saw and answered it). Only the network case queues; API errors keep their
existing verbatim handling (409 feature-off link, 422/500 messages), and a 5xx is
never queued because the server may already have processed the write. The offline
capture shows a distinct success-variant state (`role="status"`): *"Saved on this
device — will send automatically when you're back online."* A queued same-day entry is
shown on page load with its values, and a new submission replaces it (on an online
success the queued same-day entry is removed — the newer answers supersede it).

### 3. Sync: honest dates — the backend accepts `check_in_date`

**Finding (read before building):** `POST /adl` does NOT force today's date.
`AdlCheckInIn.check_in_date: date | None` (backend/app/schemas/ingestion.py) is used
verbatim by the route (`day = body.check_in_date or now.date()`), with only a
far-future guard (> UTC+14 → 422); past dates are accepted and supersede within their
own day. The online client already sends the local date. So the flush sends every
queued entry with the date it was **captured** on — no entry is ever re-dated to
"today", and no backdating gap exists that would force dropping stale entries. (Had
the backend not accepted a client date, stale entries would have been dropped with a
notice rather than submitted under a false date — honest data over fabricated dates;
that policy survives in the 409/422 handling below.)

Trigger matrix (`offlineSync.ts` + the invisible `OfflineCheckInSync`, mounted in the
authenticated patient area only — no anonymous POSTs):

| Trigger | When |
|---|---|
| App boot | once the auth restore lands (`status === 'authenticated'`) |
| `window 'online'` | every event while the session lasts |
| After a successful new submission | CheckInPage flushes remaining (older) days |

Flush semantics: entries post oldest day first; **single-flight** (repeated 'online'
events / overlapping triggers share one pass); per-entry outcomes:

- **success** → removed from the queue; the page shows the server's real response.
- **409/422** → the server refused the content; a retry can never succeed, so the
  entry is DROPPED and the refusal detail is surfaced **once** ("An offline check-in
  from Jul 14 couldn't be sent: …") via a consume-once notice buffer.
- **network error** → stop; the rest stays queued for the next trigger.
- **401 (auth expired mid-flush)** → stop, entry left queued; if the expiry also
  cleared the session, the clearSession wiring has already emptied the queue — the
  privacy rule (queued answers never outlive the session) deliberately wins over
  retry.
- **other 5xx** → stop and retry on a later trigger.

Client-vs-server clock: `check_in_date` is the patient's local day and the server
accepts up to UTC+14, the same assumption the online path already makes; a pathological
clock skew surfaces as the 422 drop-with-notice, never silent data loss.

## Verification boundary

- **jsdom units (20 new):** queue replace-same-day/clock-injection/corruption/storage
  failure; clear-on-clearSession incl. driving the real deletion flow; the
  network-vs-API split (TypeError queues; 500 does not); flush matrix (dates honest +
  oldest-first, single-flight, 409/422 drop + one-shot notice, network stop, 401 stop);
  boot/online/anonymous triggers; the offline→online page flip.
- **Real browser (Playwright, built bundle):** `e2e/patient/checkin-offline.spec.ts`
  submits with the network severed (`context.setOffline(true)` for `navigator.onLine`
  + the real 'online' event, PLUS `route.abort('internetdisconnected')` because route
  interception can still fulfill under emulated offline), asserts the saved-on-device
  state, restores connectivity, and asserts the mock **recorded** the POST with the
  true local date and the UI flipped to the synced result — zero console errors. The
  ADR-0022 allowlist gains exactly one status-specific line,
  `net::ERR_INTERNET_DISCONNECTED` (benign-by-design for this spec: the failure IS the
  scenario and the app handles it); any other net error still fails the gate, proven
  in the self-check spec.
- **Not covered here:** true airplane-mode behavior on a physical device (the 'online'
  event source is the OS); the web/Chromium emulation is the proxy, per ADR-0023's
  device-verification boundary.

## Alternatives considered

- **sessionStorage** — rejected: dies with the tab; offline capture must survive an
  app restart (see §1).
- **IndexedDB / a sync library** — rejected: the payload is at most a handful of
  ~100-byte entries; localStorage + a pure module is the boring, testable fit.
- **Service-worker Background Sync** — rejected for now: adds a SW lifecycle to an app
  that has none, is unevenly supported inside the Capacitor WebView, and the in-app
  triggers cover the real cases (the app must be open to check in anyway).
- **Submitting stale entries as "today"** — rejected outright: fabricated
  `check_in_date` is a data-integrity violation (ADR-0006). Moot here because the
  backend accepts the true date, but recorded so the rule survives API changes.
- **Retrying 409/422 forever** — rejected: the server refused the content; honest
  surfacing once beats a silent endless retry loop. Dropped entries are gone — acceptable
  because the refusal detail tells the patient why.
