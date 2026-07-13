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

## Remaining (build order)

| # | Portion | Built | Tested | Merged | Notes |
|---|---|---|---|---|---|
| 1 | Feature toggles API — expose Capability/PatientCapability (model exists, no endpoints); patient self-toggles (B2C) + clinician-managed toggles, consent-aware | ✅ | ✅ 100% cov | ⏳ PR #4 | ADR-0013; enforcement seam live on POST /adl + /labs + EMR pull, remaining consumers noted in the ADR |
| 2 | BioMech PDF ingest module (V1) — parse balance/gait report PDFs into research-grade Observations (SourceType.biomech); ingest + graph only | ◻️ | ◻️ | ◻️ | Separate module by design |
| 3 | Patient graphing/trends UI — from mockups/patient-app.html against the existing API | ◻️ | ◻️ | ◻️ | Mockup approved |
| 4 | Clinician UI — from mockups/clinician-app.html (panel, cross-source trend table, non-diagnostic) | ◻️ | ◻️ | ◻️ | Mockup approved |
| 5 | Hardening pass — invitation rate limiting (ADR-0012 deferral), durable secret-manager adapter, DB-backed pending-auth store, ops-auth surface to replace bootstrap token | ◻️ | ◻️ | ◻️ | Deferred follow-ups, all documented in ADRs/deps.py |

## Deferred (not scheduled)

- BioMech API/SDK ingestion (V2)
- Mobile app (biometric login)
- EMR production/sandbox registrations (Epic/Cerner app enrollment)
