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

### Preference lifecycle (logout, deletion, shared devices, revoked permission)

The device-preference decision has lifecycle consequences; each is deliberate:

- **Survives logout.** Signing out does NOT cancel the notification or clear the
  preference — the reminder belongs to the phone, its content is fixed and PHI-free
  (two constants, no name, no data), and a signed-out tap on it simply lands on the
  login screen. Defensible per-device semantics: a patient who signs out tonight
  and back in tomorrow keeps the habit nudge they configured.
- **Cleared on account deletion.** The danger-zone flow (ADR-0027) calls the seam's
  `disableReminderSilently()` on success — cancel the scheduled notification AND
  remove the stored preference — so a deleted account never keeps nudging this
  device and a future signup does not inherit a dead account's preference. It is
  best-effort by construction (never throws, every error swallowed): deletion must
  never fail because a notification cancel did.
- **A second user on a shared device inherits it.** If patient A enabled the
  reminder, logged out, and patient B signs up/in on the same device, B inherits an
  enabled, PHI-free "Daily check-in" nudge until they change it in Settings.
  Accepted and stated: the content discloses nothing about A, and B sees the
  toggle honestly "On" with the time, two taps from off.
- **Permission revoked after enabling.** The stored preference stays "on" (it is
  the patient's intent), but nothing fires: the launch re-assert schedules nothing
  (it only *checks* permission — never a launch prompt), and the Settings card
  probes the permission on mount and renders the system-settings guidance
  (`role="status"`) instead of a clean "On" state that nothing backs.

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
  pinned in a test comment the Style.Dark way). One **fixed notification id** —
  re-scheduling replaces the pending alarm (the Android implementation uses
  `FLAG_CANCEL_CURRENT`), so enable/re-enable/time-change never stacks duplicates.
- **Delivery is APPROXIMATE on modern Android — an honest limit, not a bug.**
  `allowWhileIdle: true` is requested, but it does not buy what its name suggests:
  without the `SCHEDULE_EXACT_ALARM` permission, Android 12+ treats the alarm as
  **inexact** (the OS may defer and batch the first fire), and the plugin's
  post-fire re-registration of the `on` schedule uses a **plain non-wakeup alarm
  that ignores `allowWhileIdle`** (verified in the plugin's Android source) — so
  from day 2 onward a device in Doze may not show the nudge until it next wakes.
  Net: the reminder arrives *around* the chosen time, not *at* it.
  **Deliberate non-adoption (optional follow-up):** the plugin supports the
  exact-alarm settings flow plus the `SCHEDULE_EXACT_ALARM` manifest permission,
  which would restore exactness — a daily wellness nudge does not justify asking
  the patient for exact-alarm privileges, so this is recorded as a conscious
  non-adoption for now, revisitable if approximate delivery proves inadequate.
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
  hour/minute + the repeating `on` form, cancel-on-disable, deletion cleanup,
  permission-denied, permission probe, re-assert paths, web no-ops, PHI-free
  constants) and the card (toggle, time reschedule incl. failure keeping the old
  time, empty-time guards, mount permission probe, pending states, denied guidance,
  web fallback) via injected/local-module mocks; deletion-silences-the-reminder and
  logout-keeps-it through the real delete-account flow; the web target unregressed —
  unit tests (coverage ≥90 all four) and the **32-spec** Playwright suite (new spec:
  the card's web fallback in the built bundle), zero console errors; `cap sync`
  warning-free; prod audit + license + secret scans clean.
- **Proven by CI:** the plugin compiles into the APK (`mobile` job).
- **User's step (on-device only):** an actual notification arriving around the
  chosen time (see the approximate-delivery limit above), the Android 13+ permission
  prompt, and the reboot-survival behavior — `npx cap run android`, enable the
  reminder, and let it fire.

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
