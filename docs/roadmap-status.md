# Roadmap status board

The single source of truth for what remains and where each portion stands.
Updated every development-loop cycle; one portion = one small PR (working
agreement). States: **Built** (code complete on a branch), **Tested** (full gate
green: ruff + mypy --strict + pytest incl. live-Postgres integration, adversarial
review findings fixed), **Merged** (on `main`).

## Shipped

| Portion | Built | Tested | Merged |
|---|---|---|---|
| Auth — Argon2id + JWT access/refresh (ADR-0010) | ✅ | ✅ | ✅ |
| FHIR/LOINC lab intake + reference ranges (ADR-0007) | ✅ | ✅ | ✅ |
| EMR patient pull — SMART on FHIR OAuth/PKCE (ADR-0008/0009) | ✅ | ✅ | ✅ |
| ADL daily check-ins + supersede-by-revision (ADR-0006) | ✅ | ✅ | ✅ |
| Trajectory engine — explainable direction/confidence/signals | ✅ | ✅ | ✅ |
| Postgres durability — repositories, migrations, request transactions | ✅ | ✅ | ✅ |
| AI narrative layer — validated, BAA-gated, off-request-path (ADR-0011) | ✅ | ✅ | ✅ |
| Clinician surface — consent-gated panel/views, invitations (ADR-0012) | ✅ | ✅ 100% cov | ✅ PR #3 |
| Feature toggles API — server-enforced capabilities, B2C + clinician-managed, consent-aware (ADR-0013) | ✅ | ✅ 100% cov | ✅ PR #4 |
| BioMech PDF ingest module (V1) — balance/gait report PDFs into research-grade Observations (ADR-0014) | ✅ | ✅ | ✅ PR #5 |
| Patient graphing/trends UI — from mockups/patient-app.html against the existing API (ADR-0015) | ✅ | ✅ | ✅ PR #6 |
| Clinician UI — from mockups/clinician-app.html (panel, cross-source trend table, non-diagnostic) (ADR-0016) | ✅ | ✅ | ✅ PR #7 |
| Hardening pass — invitation rate limiting, durable pending-auth store, encrypted token vault with deletion-on-revoke, hardened ops gate, blocking Python security/license scans (ADR-0017) | ✅ | ✅ 100% cov | ✅ PR #8 |

## Remaining (build order) — V2

**Wave 1 — Production readiness** ✅ **COMPLETE** (decision 2026-07-14: V1 becomes
deployable and operable before new surface area). All five portions built, adversarially
reviewed, and merged (PRs #9, #10, #12, #14, #15).

| # | Portion | Built | Tested | Merged | Notes |
|---|---|---|---|---|---|
| 1 | Deployment & infrastructure — backend/frontend containers (multi-stage, non-root, secret-free), health/readiness endpoints, PHI-free structured request logging, runtime-config frontend, staging compose, deploy + backup/restore runbooks, image-build CI (ADR-0018) | ✅ | ✅ 100% cov | ✅ PR #9 | |
| 2 | Ops-auth surface — replace OPS_BOOTSTRAP_TOKEN with real ops identities for provisioning (ADR-0019) | ✅ | ✅ 100% cov | ✅ PR #10 | per-operator ops accounts + require_ops; clinician provisioning needs an ops bearer (real actor attribution); OPS_BOOTSTRAP_TOKEN narrowed to self-closing first-ops bootstrap; per-operator deactivation; migration 0005 |
| 3 | Wire the remaining toggles — `emr_connect` gating /emr connect flow, `ai_narrative` gating narrator scheduling, `share_with_clinic` gating clinician reads; each flips enforced=True with its own consent-interaction decision (ADR-0013/ADR-0020) | ✅ | ✅ 100% cov | ✅ PR #12 | All three wired in one PR (ADR-0020): emr_connect gates connect+callback (connect-vs-pull split; revoke never blockable); ai_narrative ANDs with the BAA gate as an in-handler branch (200 stays deterministic, no disclosure audit when off); share_with_clinic is a patient-held consent control gating clinician reads via ONE `_may_read_patient` predicate (panel drop + neutral 404 + capability-write 404), carved out of clinician toggle-authority so the patient always controls it even when clinically managed. Frontend fixtures/tests updated (reads `enforced` from API). |
| 4 | Observability & ops — error tracking (self-hosted-friendly), metrics, alerting hooks, Postgres backup drill; compliance pack (HIPAA ops checklist, BAA inventory, incident-response runbook) | ✅ | ✅ 100% cov | ✅ PR #14 | ADR-0021. PHI-free `GET /metrics` (prometheus_client; method/route-template/status labels — never raw path; app_up, DB pool, subject-free AI-disclosure counter; auth-denials/rate-limits read off the status label). `MetricsMiddleware` + `ErrorReportingMiddleware` compose inside the outermost logging middleware (logging stays index 0). Error seam mirrors the Narrator: off-by-default, self-hostable, PHI-scrubbing (whitelist event — never the exception message), fail-safe. Alert rules + scrape/collector wiring in `docs/ops/observability.md`. Tested backup drill script + `SECRET_STORE_KEY` trap reinforced. Compliance pack under `docs/compliance/` with honest [CE] boundaries. |
| 5 | Browser-verify the shipped patient + clinician UIs (Playwright/Chromium: built app renders + key flows work + ZERO new console errors) — retroactive Definition-of-Done closure for ADR-0015/0016 UI portions (msw/unit tests are not sufficient proof) | ✅ | ✅ | ✅ PR #15 | ADR-0022. 29 committed Playwright specs (patient + clinician + 2 gate self-checks) drive the REAL `vite build`/`vite preview` bundle in the pre-installed Chromium (rev 1194), API mocked in-browser mirroring `src/test/server.ts`, runtime `/config.js` (ADR-0018) exercised. Auto zero-console-errors gate (`pageerror` + `console.error`, allowlist pinned to the designed 401/404/409/422 only — a 500 fails) on every spec, with a self-check proving the gate fails on a real fault. Proves the ADR-0020 §3(b) `share_with_clinic` read-only property in a real browser. Dedicated blocking CI `e2e` job (browser installed CI-only). Existing gates untouched. |

**Wave 2 — Mobile app** ✅ **COMPLETE (Android)** (PRs #17, #18, #19): Capacitor wrap of the existing SPA (ADR-0023 —
professional staged approach; revisit trigger recorded: native rebuild only if
device/HealthKit/BLE integration lands). **Android-first per user (ready to go); iOS
PENDING the user's DUNS + Apple-ID switch — do not collect Apple credentials until iOS
submission.**

| # | Portion | Built | Tested | Merged | Notes |
|---|---|---|---|---|---|
| 1 | Capacitor scaffolding + Android platform — `@capacitor/core` (prod, MIT) + cli/android (dev), `capacitor.config.ts`, generated `android/` native project, cap npm scripts, keystore-safe `.gitignore`, ESLint/Prettier exclude the native tree; CI `mobile` job assembles a debug APK (ADR-0023) | ✅ | ✅ | ✅ PR #17 | Scaffolding only — no web behavior change. Web target unregressed (29 Playwright specs green), `cap sync` works, prod audit + license gates pass, no secret-scan hits; CI `mobile` job assembled the debug APK. Security-review fixes: allowBackup=false, uncommented google-services/keystore ignores, secret-scan hardened, setup-android pinned to a SHA. |
| 2 | Secure token storage + biometric unlock — move the refresh token off web `sessionStorage` into the OS secure store (Keystore) on native, biometric gate before revealing the session; web posture (ADR-0015) unchanged as the fallback so the E2E suite is unaffected | ✅ | ✅ | ✅ PR #18 | ADR-0024. Platform-selected refresh-token backend (WebBackend sessionStorage / NativeBackend Keystore via @aparajita/capacitor-secure-storage, Cap-6-pinned); sync `peek` + async `load` prime so the sync restore-decision timing is unchanged on web. Biometric gate (@aparajita/capacitor-biometric-auth) via `resolveNativeRestore` (unit-tested decision logic). Access token stays memory-only. Review fixes: biometric gate fails CLOSED on a gate error (open only for genuinely-unenrolled devices), durable logout-delete retries, and `fileParallelism:false` removes a parallel-worker unit-test flake. Verified: web unregressed (146 unit + 29 E2E green, deterministic), native building blocks unit-tested via injection/local mocks; APK-compile proven by the CI `mobile` job; on-device Keystore/biometric is the user's `npx cap run android`. |
| 3 | Native shell — status bar / splash / safe-area insets / hardware back button (ADR-0025). **OAuth-callback handling DEFERRED to Wave 3** (no EMR connect UI exists yet to hook it to; the native app-scheme/appUrlOpen handler ships with the connect UI, after sandbox registration). | ✅ | ✅ | ✅ PR #19 | ADR-0025. Official Cap-6 plugins (@capacitor/status-bar, splash-screen, app; all MIT). `useNativeShell`/`initNativeShell` no-op on web (gated by `isNativePlatform`), so the 29 E2E specs are unchanged; hardware back navigates history / exits at root (`backAction` unit-tested); splash hidden on React mount (no white flash); safe-area via `viewport-fit=cover` + `env(safe-area-inset-*)` (0 on web). Verified: 149 unit + 29 E2E green, `cap sync` warning-free, prod audit + license clean; APK-compile is the CI `mobile` job; on-device look is the user's `npx cap run android`. |

| 4 | Play release prep — release signing (git-ignored `keystore.properties` + Play App Signing, unsigned fallback), manual `release-android.yml` AAB workflow (optional signing secrets, keystore shredded), Play runbook + listing pack (Data Safety draft from actual data flows) + privacy-policy scaffold (ADR-0026) | ✅ | ⏳ | ⏳ | Publisher decided 2026-07-14: **the Advanced Health and Wellness Group org account** (needs the org's DUNS at signup — user-side). No credential collected. Known gaps recorded: account/data **deletion flow REQUIRED before store submission** (hard Play rule — new roadmap item below), production backend deployment, HIPAA validation + BAAs before real data. Internal testing possible before those. |

**Wave 2 Android done: the app installs, stores tokens in the Keystore + biometric-unlocks, and has a polished native shell; Play release prep staged.** iOS still PENDING the user's DUNS + Apple-ID switch; the SMART OAuth native handler rides with Wave 3's EMR-connect UI.

**Required pre-store portion (from ADR-0026):** patient-facing **account & data deletion flow** (in-app + API) — a hard Google Play requirement for apps collecting user data, and good HIPAA hygiene regardless. **Built ✅ / Tested ✅ (100% cov on new code; live-Postgres integration green) / Merged ⏳** — ADR-0027: `DELETE /auth/me` with password re-auth (Argon2id), transactional FK-safe destruction of every patient-owned row (vault secrets purged via the ADR-0017 revoke seam), audit history RETAINED anonymous via `audit_event.patient_id` ON DELETE SET NULL (migration 0006), never blockable by toggles/kill switches; Settings "Danger zone" card (password + acknowledgment + two-tap confirm) landing on `/login` with a transient deleted notice; 30th Playwright spec drives the built bundle with zero console errors.

**Wave 3 — EMR registrations**: Epic/Cerner sandbox enrollment — operator runbook at
[`docs/emr/sandbox-registration-runbook.md`](emr/sandbox-registration-runbook.md)
(signup → app registration → redirect URIs → smoke test; also surfaces the code
changes needed: per-provider client ids, browser-reachable callback, scope alignment) —
plus the provider config surface, then production enrollment. **Includes the patient EMR-connect UI + the
native SMART OAuth-callback handler deferred from Wave 2 Portion 3** (custom app scheme +
`@capacitor/app` `appUrlOpen` + in-app browser), so the connect flow and its native handler
ship and verify together against a registered sandbox.

**Wave 4 — Reimbursement-enabling features (RTM-first)** — build the app capture/export
that could enable a covered entity to pursue a compliant claim, pending compliance
validation, prioritized for RTM given the
BioMech musculoskeletal/gait/balance + ADL self-report streams (see
[`docs/product/reimbursement-analysis.md`](product/reimbursement-analysis.md) §7 for the
prioritized backlog: parameterized ≥N-day adherence counter, interactive-time ledger,
episode/setup event, billing-consent scope, PHI-safe billing-evidence export, BioMech
device-provenance strengthening, and the FDA device-status ADR). **PENDING compliance
validation** of the reimbursement analysis by a certified professional coder +
compliance/legal **before any build** — this Wave enables billing pathways, it does not
authorize billing, and nothing starts until that sign-off exists. The review packet for
that sign-off is
[`docs/product/reimbursement-signoff-packet.md`](product/reimbursement-signoff-packet.md)
(the exact decisions requested, reviewable assertions, the FDA device-status question, and
the sign-off sheet); market context on products already billing these codes is in
[`docs/product/reimbursed-apps-comparison.md`](product/reimbursed-apps-comparison.md).

## Deferred (not scheduled)

- BioMech API/SDK live ingestion (decision 2026-07-14: PDF stays primary; revisit
  when BioMech provides API/SDK documentation — the ADR-0014 seam absorbs it)
