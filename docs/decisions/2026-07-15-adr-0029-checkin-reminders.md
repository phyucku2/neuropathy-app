# ADR-0029 — Daily check-in reminder (native local notification)

- **Status:** Accepted (Wave 5 — patient experience, portion 1)
- **Date:** 2026-07-15
- **Builds on:** ADR-0023 (Capacitor, Android-first), ADR-0024 (platform seams,
  Cap-6 plugin pinning), ADR-0025 (native shell init, splash-before-listeners),
  ADR-0022 (browser E2E DoD), ADR-0006 (ADL check-ins — the thing being nudged)

## Context

The ADL check-in (ADR-0006) is the app's daily habit, and daily habits need a nudge.
A reminder is a device concern: it must fire when the app is closed, which on the web
platform this app has no reliable primitive for (no push backend exists, and a
service-worker notification without one is a false promise). The native shell
(ADR-0023) can do this properly with a local notification — no server involved at all.

## Decision

A patient-configurable **daily local notification** ("Daily reminder" card in
Sources/Settings): toggle + time (default 09:00), **native-only**, via
**`@capacitor/local-notifications@^6.1.3`** (official, MIT) — pinned to the
**Capacitor-6 line** the ADR-0024 way: the current 8.x line's devDeps pin
`@capacitor/cli` ^8 (Cap 8), so the plugin is pinned down to `6.x`, whose devDeps pin
`@capacitor/cli` ^6 and whose peerDeps name `@capacitor/core` ^6; `npx cap sync
android` runs warning-free on it. Prod `npm audit` and the license allowlist stay
green. On web the card renders the toggle disabled with an honest "Reminders are
available in the mobile app" — never a control that silently does nothing.

### The preference is device-local (localStorage), not server state

`neuropathy.checkin_reminder` (`{enabled, hour, minute}`) lives in `localStorage` on
the device, deliberately NOT on the server:

- **Per-device semantics are the correct semantics** — a reminder belongs to the
  phone it fires on; a phone and a tablet can legitimately want different times, and
  a reminder enabled on one device should not silently appear on another.
- **No server round-trip / works offline** — enable, change, disable all work with no
  connectivity, and no backend surface (schema, endpoint, migration) is added for
  what is purely a client alarm.
- **It is not PHI** — a boolean and a wall-clock time; losing it (app data clear)
  loses nothing but a preference the patient can re-set in two taps.

### Notification content is fixed and PHI-free — by construction

The scheduled content is two constants and nothing else: title **"Daily check-in"**,
body **"How are you feeling today? 30 seconds is all it takes."** Notifications
render on the lock screen and in the notification shade — below the app's auth
boundary — so no health data, score, trend, or name may ever appear there (the
"PHI can leak below the app" lesson). The constants are pinned by unit test; any
future dynamic content in a notification needs its own ADR.

### The seam (`src/native/reminders.ts`)

Follows the nativeShell/externalBrowser pattern (ADR-0024/0025): pure logic + an
injectable plugin accessor (defaulting to `LocalNotifications`), so every decision is
unit-tested off-device. `getReminderState()` / `enableReminder(hour, minute)` /
`disableReminder()` / `reassertReminder()`.

- **Schedule shape:** the plugin's cron-like **`schedule.on {hour, minute}`**
  repeating form (Cap-6 `Schedule.on`, definitions.d.ts) — Android computes the next
  wall-clock match and re-registers the following trigger after each fire, i.e. a
  daily repeat at local time (`repeats` belongs to the one-shot `at` form, not `on`;
  pinned in a test comment the Style.Dark way). `allowWhileIdle: true` lets it fire
  in Doze. One **fixed notification id** — re-scheduling replaces the pending alarm
  (the Android implementation uses `FLAG_CANCEL_CURRENT`), so enable/re-enable/
  time-change never stacks duplicates.
- **Permission-denied is a RESULT, not an error:** `enableReminder` returns
  `'permission-denied'` when the OS refuses (Android 13+ runtime permission); the
  card renders inline guidance (`role="status"`) pointing at the phone's system
  settings. A denied prompt is a normal user choice; nothing is scheduled and the
  preference stays off (never a stored "on" the OS won't honor — the enforced-flag
  honesty rule). A schedule fault likewise persists nothing.
- **Web:** `'unavailable'` no-op behind `isNativePlatform()` — the browser bundle and
  E2E suite never invoke the plugin.

### OEM reboot caveat → re-assert at launch

Stock Android drops `AlarmManager` alarms on reboot; the plugin ships a BOOT_COMPLETED
receiver that restores them, but several OEM batteries/task-killers (and some
app-update paths) drop them anyway. So `initNativeShell` **re-asserts** the reminder
on every native launch: if the stored preference says enabled, re-schedule the same
fixed id (idempotent). The re-assert is **fire-and-forget AFTER `SplashScreen.hide()`**
— it must never delay or break the reveal (the ADR-0025 splash-before-listeners
lesson); its promise is unawaited and a rejection is swallowed. It uses
`checkPermissions` (never `requestPermissions`) so a cold launch can never pop a
permission dialog; if permission was revoked in system settings it schedules nothing
and leaves the preference for the Settings card to explain.

## Verification boundary (honest)

- **Verified here:** the seam's full decision table (exact schedule shape incl.
  hour/minute + the repeating `on` form, cancel-on-disable, permission-denied,
  re-assert paths, web no-ops, PHI-free constants) and the card (toggle, time
  reschedule, pending states, denied guidance, web fallback) via injected/local-module
  mocks; the web target unregressed — 212 unit tests (coverage ≥90 all four) and the
  **32-spec** Playwright suite (new spec: the card's web fallback in the built
  bundle), zero console errors; `cap sync` warning-free; prod audit + license +
  secret scans clean.
- **Proven by CI:** the plugin compiles into the APK (`mobile` job).
- **User's step (on-device only):** an actual notification arriving at the chosen
  time, the Android 13+ permission prompt, and the reboot-survival behavior —
  `npx cap run android`, enable the reminder, and let it fire.

## Alternatives considered

- **Server-side push (FCM)** — rejected: needs a push backend, a Google service
  dependency, and a token registry for what a purely local alarm does better; also
  a PHI-adjacent egress seam this portion doesn't need.
- **Web reminders via service-worker Notifications** — rejected: without a push
  backend the page must be open for a timer to fire, which is not a reminder; the
  honest web story is the fallback message.
- **Persist the preference server-side** — rejected (see above: per-device semantics,
  offline, no new backend surface for a non-PHI device preference).
- **`schedule.every: 'day'`** — rejected: it repeats relative to the moment of
  scheduling, not at a chosen wall-clock time; `on {hour, minute}` is the calendar
  form the feature means.
