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

## Remaining (build order)

| # | Portion | Built | Tested | Merged | Notes |
|---|---|---|---|---|---|
| 1 | Patient graphing/trends UI — from mockups/patient-app.html against the existing API | ✅ | ✅ | ◻️ | ADR-0015; Vite + React + recharts in `frontend/`; msw-tested, 90%+ coverage gate in CI |
| 2 | Clinician UI — from mockups/clinician-app.html (panel, cross-source trend table, non-diagnostic) | ◻️ | ◻️ | ◻️ | Mockup approved |
| 3 | Hardening pass — invitation rate limiting (ADR-0012 deferral), durable secret-manager adapter, DB-backed pending-auth store, ops-auth surface to replace bootstrap token | ◻️ | ◻️ | ◻️ | Deferred follow-ups, all documented in ADRs/deps.py |

## Deferred (not scheduled)

- BioMech API/SDK ingestion (V2)
- Mobile app (biometric login)
- EMR production/sandbox registrations (Epic/Cerner app enrollment)
