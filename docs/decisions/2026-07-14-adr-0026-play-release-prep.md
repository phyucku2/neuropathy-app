# ADR-0026 — Google Play release preparation (Android)

- **Status:** Accepted
- **Date:** 2026-07-14
- **Relates to:** ADR-0023 (Capacitor scaffold), ADR-0024 (secure tokens), ADR-0025 (native shell)

## Context

Wave 2 made the Android app real (installable, secure tokens, native shell). The owner decided
to publish under **their organization's Play Console account (Advanced Health and Wellness Group)** (they own the IP; BioMech is
licensee). This portion prepares everything account-independent for a Play release, without
collecting any credential.

## Decision

1. **Release signing via a git-ignored `keystore.properties` + Play App Signing.** The
   `app/build.gradle` release build signs with the owner-generated **upload key** when
   `frontend/android/keystore.properties` exists and **falls back to unsigned when absent** —
   so the CI compile-proof job and fresh clones are unaffected. Play App Signing escrows the
   real app-signing key (upload-key loss is recoverable). `versionName` tracks `package.json`
   (0.1.0); `versionCode` bumps on every Play upload.
2. **A manual `release-android.yml` workflow** (workflow_dispatch; third-party actions SHA-pinned, GitHub-first-party actions tag-pinned — the same posture as ci.yml) builds
   the web bundle → `cap sync` → `bundleRelease` (AAB — Play requires bundles, not APKs).
   Signing secrets (`ANDROID_KEYSTORE_BASE64` + passwords/alias) are optional: present →
   signed AAB artifact; absent → unsigned smoke AAB. Keystore material is written to the
   runner temp dir and shredded in an `always()` step.
3. **Operator docs, honestly gated:** `docs/mobile/play-release-runbook.md` (account, keystore,
   upload, tracks), `docs/mobile/play-listing-pack.md` (Data Safety draft answers grounded in
   the actual data flows, health-app declaration, checklist), and
   `docs/legal/privacy-policy-draft.md` (scaffold — **counsel review required**).

## Known gaps recorded (pre-production, not pre-internal-testing)

- **Account/data deletion flow is not shipped** — a hard Play requirement for apps collecting
  user data; added to the roadmap as a required pre-submission portion.
- **No deployed production backend**; the store artifact's bundled `config.js` must carry the
  production API base URL.
- **HIPAA validation + BAAs** before real patient data (docs/compliance/).

Internal testing (synthetic accounts) is possible before all three; production is not.

## What was NOT done (deliberately)

- No Play account, DUNS, or credential collected — the runbook tells the owner how.
- No minification of the native shell (R8 buys little; the web bundle is already minified;
  plugin reflection risk).
- No store assets committed yet (icon/feature graphic/screenshots) — follows the listing
  checklist when the go-to-market name is confirmed.

## Verification boundary

No Android SDK in this environment: the gradle changes compile-verify in CI (`mobile` job
still runs `assembleDebug` with NO keystore present — proving the unsigned fallback), and the
release workflow is validated by YAML parse + a dry review; its first real run is on GitHub.
Nothing in the web target changed (docs + gradle + a new workflow only).
