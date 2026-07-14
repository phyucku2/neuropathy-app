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

**Wave 1 — Production readiness** (decision 2026-07-14: V1 becomes deployable and
operable before new surface area).

| # | Portion | Built | Tested | Merged | Notes |
|---|---|---|---|---|---|
| 1 | Deployment & infrastructure — backend/frontend containers (multi-stage, non-root, secret-free), health/readiness endpoints, PHI-free structured request logging, runtime-config frontend, staging compose, deploy + backup/restore runbooks, image-build CI (ADR-0018) | ✅ | ✅ 100% cov | ✅ PR #9 | |
| 2 | Ops-auth surface — replace OPS_BOOTSTRAP_TOKEN with real ops identities for provisioning (ADR-0019) | ✅ | ✅ 100% cov | ✅ PR #10 | per-operator ops accounts + require_ops; clinician provisioning needs an ops bearer (real actor attribution); OPS_BOOTSTRAP_TOKEN narrowed to self-closing first-ops bootstrap; per-operator deactivation; migration 0005 |
| 3 | Wire the remaining toggles — `emr_connect` gating /emr connect flow, `ai_narrative` gating narrator scheduling, `share_with_clinic` gating clinician reads; each flips enforced=True with its own consent-interaction decision (ADR-0013) | ◻️ | ◻️ | ◻️ | One PR per key or grouped — judge at build time |
| 4 | Observability & ops — error tracking (self-hosted-friendly), metrics, alerting hooks, Postgres backup drill; compliance pack (HIPAA ops checklist, BAA inventory, incident-response runbook) | ◻️ | ◻️ | ◻️ | Docs + code |
| 5 | Browser-verify the shipped patient + clinician UIs (Playwright/Chromium: built app renders + key flows work + ZERO new console errors) — retroactive Definition-of-Done closure for ADR-0015/0016 UI portions (msw/unit tests are not sufficient proof) | ◻️ | ◻️ | ◻️ | Near-term; DoD gap-fill, no new surface |

**Wave 2 — Mobile app**: Capacitor wrap of the existing SPA (decision 2026-07-14 —
professional staged approach; ADR to record the revisit trigger: native rebuild only
if device/HealthKit integration lands). Biometric unlock + Keychain/Keystore token
storage replace the web sessionStorage posture.

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
