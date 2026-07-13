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

## Remaining (build order)

| # | Portion | Built | Tested | Merged | Notes |
|---|---|---|---|---|---|
| 1 | Hardening pass — invitation rate limiting (ADR-0012 deferral), encrypted-at-rest DB token vault, DB-backed single-use pending-auth store, bootstrap-token hardening (min length + denied-attempt audit; a dedicated ops-auth surface still replaces it at production readiness), CI's Python pip-audit/pip-licenses steps now blocking | ✅ | ✅ 100% cov | ◻️ | ADR-0017; frontend untouched |

## Deferred (not scheduled)

- BioMech API/SDK ingestion (V2)
- Mobile app (biometric login)
- EMR production/sandbox registrations (Epic/Cerner app enrollment)
