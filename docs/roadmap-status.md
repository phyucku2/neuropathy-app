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

**Wave 2 — Mobile app** (IN PROGRESS): Capacitor wrap of the existing SPA (ADR-0023 —
professional staged approach; revisit trigger recorded: native rebuild only if
device/HealthKit/BLE integration lands). **Android-first per user (ready to go); iOS
PENDING the user's DUNS + Apple-ID switch — do not collect Apple credentials until iOS
submission.**

| # | Portion | Built | Tested | Merged | Notes |
|---|---|---|---|---|---|
| 1 | Capacitor scaffolding + Android platform — `@capacitor/core` (prod, MIT) + cli/android (dev), `capacitor.config.ts`, generated `android/` native project, cap npm scripts, keystore-safe `.gitignore`, ESLint/Prettier exclude the native tree; CI `mobile` job assembles a debug APK (ADR-0023) | ✅ | ⏳ | ⏳ | Scaffolding only — no web behavior change. Verified locally: web target unregressed (tsc/eslint/prettier/vitest/build + 29 Playwright specs green), `cap sync` works, prod audit + license gates pass, no secret-scan hits. No Android SDK in this env, so on-device is the user's `npx cap run android`; the CI `mobile` job proves the APK compiles. |
| 2 | Secure token storage + biometric unlock — move the refresh token off web `sessionStorage` into the OS secure store (Keystore) on native, biometric gate before revealing the session; web posture (ADR-0015) unchanged as the fallback so the E2E suite is unaffected | — | — | — | Security-sensitive → adversarial review. Async secure-store API vs the current sync token store is the main design point. |
| 3 | Native shell + OAuth-callback handling — status bar / splash / safe-area insets / hardware back button; the SMART OAuth redirect (ADR-0009) needs an app-scheme/App-URL handler on native instead of a web redirect | — | — | — | |

**Wave 3 — EMR registrations**: Epic/Cerner sandbox enrollment (runbook + provider
config surface), then production enrollment.

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
authorize billing, and nothing starts until that sign-off exists.

## Deferred (not scheduled)

- BioMech API/SDK live ingestion (decision 2026-07-14: PDF stays primary; revisit
  when BioMech provides API/SDK documentation — the ADR-0014 seam absorbs it)
