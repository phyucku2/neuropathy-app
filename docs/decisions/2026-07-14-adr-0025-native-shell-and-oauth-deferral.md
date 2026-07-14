# ADR-0025 — Native shell polish; OAuth-callback handling deferred

- **Status:** Accepted (Wave 2, portion 3)
- **Date:** 2026-07-14
- **Relates to / extends:** ADR-0023 (Capacitor, Android-first), ADR-0009 (SMART on FHIR EMR connect)

## Context

Portion 3 of Wave 2 was scoped as "native shell polish **and** SMART OAuth-callback handling."
On inspection the frontend has **no EMR SMART connect flow** — there are no `/emr` calls,
`authorize_url` handling, or provider-picker UI in `frontend/src`. The `/emr/connect` +
`/emr/callback` endpoints exist on the backend (ADR-0009) but are not surfaced in the patient app,
and EMR **sandbox registration is Wave 3** (a prerequisite to exercising any real OAuth handshake).

Building a native app-scheme / deep-link callback handler now would be infrastructure wired to a
flow that does not exist and cannot be exercised end-to-end (no connect UI, no registered sandbox).

## Decision

**Ship the native shell polish; defer the OAuth-callback handling to when the EMR connect UI is
built (Wave 3), where the native deep-link handler belongs alongside it.**

Native shell (Android-first; all native-only, web unaffected):

- **Status bar / splash / hardware back** (`src/native/nativeShell.ts` + `useNativeShell` hook,
  official `@capacitor/status-bar`, `@capacitor/splash-screen`, `@capacitor/app`, all MIT, Cap-6
  line). `initNativeShell` is a **no-op on web** (gated by `isNativePlatform()`), so the browser
  build and the 29-spec E2E suite are unchanged. The Android **hardware back button** navigates in
  app history when the WebView can go back and **exits at a root screen** (never traps the user) —
  the decision (`backAction`) is a pure, unit-tested function. The splash is hidden by the app
  after React mounts (`launchAutoHide:false` in `capacitor.config.ts`) so there is no white flash.
- **Safe-area insets** — `viewport-fit=cover` in `index.html` plus `env(safe-area-inset-*)` padding
  on the header (`.status-bar`, top) and tab bar (`.tabbar`, bottom). On web the insets resolve to
  `0` (fallback), so the layout is byte-for-byte unchanged.

### OAuth-callback handling — explicitly deferred (not skipped)

When the patient EMR-connect UI lands (Wave 3, after sandbox registration), it will need, on native:
a custom app URL scheme registered in `AndroidManifest.xml`, an `@capacitor/app` `appUrlOpen`
listener to catch the `code`+`state` redirect back into the app, and an in-app browser
(`@capacitor/browser`) for the authorize step — replacing the web redirect. That work is tracked as
a Wave-3 item so the native handler and the connect UI ship and verify together.

## Verification boundary (honest)

- **Verified here:** web target unregressed — 149 unit tests + the 29-spec Playwright/Chromium
  suite pass; `backAction` and the web no-op path of `initNativeShell` are unit-tested; `cap sync`
  is warning-free; prod audit + license gates green.
- **Proven by CI:** the three plugins compile into the APK (`mobile` job).
- **User's step:** the actual status-bar look, splash timing, safe-area layout on a notched device,
  and the hardware-back behavior — `npx cap run android` on a device. Cosmetic choices (status-bar
  style) are trivially tunable there.

## Alternatives considered

- **Build the native OAuth deep-link handler now** — rejected: nothing to wire it to, and no
  sandbox to verify against; it would be untestable dead code until Wave 3.
- **Build the whole EMR connect UI in this portion** — rejected: it belongs with Wave 3 EMR
  registration (the sandbox is the prerequisite), and would balloon a "shell polish" portion.
- **Auto-hide the splash (Capacitor default)** — rejected: a fixed timeout risks a white flash or a
  too-long splash; hiding on React mount is precise.
