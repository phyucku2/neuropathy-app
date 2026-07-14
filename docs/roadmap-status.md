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

## Remaining (build order)

*Empty — every planned portion has shipped. New work starts a new row here.*

## Deferred (not scheduled)

- BioMech API/SDK ingestion (V2)
- Mobile app (biometric login)
- EMR production/sandbox registrations (Epic/Cerner app enrollment)
