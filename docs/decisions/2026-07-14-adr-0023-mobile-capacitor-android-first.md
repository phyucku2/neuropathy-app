# ADR-0023 — Mobile app via Capacitor, Android-first

- **Status:** Accepted (Wave 2, portion 1 — scaffolding)
- **Date:** 2026-07-14
- **Supersedes / relates to:** ADR-0015 (token posture), ADR-0018 (runtime config), ADR-0022 (browser E2E)

## Context

Wave 1 shipped a deployable, operable web app. Wave 2 is the mobile app. The user's
direction (2026-07-14): **Android-first and ready to go; iOS deferred until the user's
DUNS + Apple-ID switch** — so nothing here collects or needs Apple credentials, and the
iOS platform is intentionally not added yet.

The existing frontend is a Vite/React SPA already proven in a real browser (ADR-0022,
29 Playwright specs against the built bundle). The mobile question is how to ship that
same app to a phone without forking the codebase or regressing the web target.

## Decision

**Wrap the existing SPA with [Capacitor](https://capacitorjs.com/), Android platform
only, as the first portion.** Capacitor runs the *same* `vite build` output (`webDir:
'dist'`) inside a native WebView shell; there is no second UI codebase. This portion is
**scaffolding only** — the native project, config, and toolchain — with no behavioral
change to the web or (yet) any native-only code paths. Secure native token storage +
biometric unlock and the native OAuth-callback handling are their own later portions.

### What this portion adds

- `@capacitor/core` (prod dep, MIT), `@capacitor/cli` + `@capacitor/android` (dev deps).
  The production dependency tree stays clean on the blocking `npm audit --omit=dev
  --audit-level=high` and the production license allowlist (verified locally).
- `frontend/capacitor.config.ts` — `appId: com.ahwg.neuropathy`, `appName:
  Neuropathy`, `webDir: dist`, `androidScheme: https` (WebView served from a secure
  `https://localhost` origin so Web Crypto / secure storage behave as on web),
  `allowMixedContent: false` (the app only talks to the API over TLS; the base URL comes
  from the ADR-0018 runtime `/config.js`). No committed `server.url` — the shipped app
  loads the **bundled** assets, never a remote dev server.
- `frontend/android/` — the generated native project skeleton (committed, per Capacitor
  convention). Build outputs (`build/`, `.gradle/`, `local.properties`), the copied web
  bundle (`assets/public`), and the generated config JSON are **git-ignored**. The
  keystore-ignore patterns (`*.jks`, `*.keystore`, `*.properties`) were **uncommented and
  extended** from Capacitor's default — a signing key is a production secret and must
  never be committable.
- npm scripts: `cap:sync`, `cap:copy`, `cap:open:android`.
- `android/` is excluded from ESLint and Prettier (it is Java/Gradle/XML plus the copied
  minified bundle — not TypeScript source).

### appId is semi-permanent

`com.ahwg.neuropathy` is the Android application id / Play Store package name. It is a
free-to-change local identifier **until the first Google Play release, after which it is
permanent.** CONFIRMED 2026-07-14: the id was switched to `com.ahwg.neuropathy` (Advanced Health and Wellness Group is the DUNS-registered publisher; ADR-0026) (it encodes the
go-to-market brand; the user owns the IP and BioMech licenses it).

## Verification boundary (honest)

This environment has Node + a JDK but **no Android SDK** (`ANDROID_HOME` unset). So this
portion is verified to the limit of what is possible here, and no further:

- **Verified here:** the web target is unregressed — `tsc`, ESLint (zero warnings),
  Prettier, Vitest, `vite build`, and the full 29-spec Playwright/Chromium suite all pass
  with Capacitor added; `npx cap sync android` succeeds; the production audit + license
  gates pass; no secret-scan hits.
- **NOT verifiable here (deferred, not skipped):** compiling the native project to an APK
  (`./gradlew assembleDebug`) and running it on an emulator/device. That needs the
  Android SDK. It is wired into CI as a dedicated **`mobile`** job (sets up the SDK and
  runs a debug assemble — debug signing needs no keystore), and real-device smoke is the
  user's `npx cap run android`. A green web suite proves the *app*; the `mobile` CI job
  proves it *compiles into an Android package*; only a device proves the *shell*.

## Alternatives considered

- **React Native / native rebuild** — rejected now: it forks the UI codebase for no
  present benefit. The revisit trigger is device-native integration (HealthKit / Google
  Fit / BLE to the BioMech device); recorded so a future ADR can flip this.
- **PWA only (installable web)** — rejected: no app-store presence, weaker secure-storage
  and biometric story, and iOS PWA constraints. Capacitor keeps the PWA option open while
  giving a store artifact.
- **Add iOS now** — deferred by user direction (DUNS + Apple-ID switch pending); adding it
  would also pull in Apple credential/signing concerns we deliberately avoid.
