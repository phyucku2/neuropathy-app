# Backend — neuropathy-app

Ingest (BioMech, labs, ADL) → unified longitudinal record → graphs + AI
health-trajectory analysis. Stack and rationale: **ADR-0004**. Product scope: **ADR-0003**.

**Stack:** Python 3.12 · FastAPI (async) · PostgreSQL · SQLAlchemy 2.0 (async) ·
Alembic · Pydantic v2.

## Layout

```
app/
  core/        settings (env-driven; no hard-coded secrets)
  db/          async engine, session, declarative base + mixins
  models/      SQLAlchemy models
                 patient           — identity + tenancy (B2C vs clinic)
                 observation       — the unified longitudinal record (all sources)
                 capability        — capability registry + per-patient toggle authority
                 audit             — append-only PHI/config audit log
  schemas/     Pydantic API models (see trajectory.py — the centerpiece view)
  api/routes/  thin HTTP routers
  services/    business logic (capabilities, ingestion, trajectory, audit)
  ingestion/   source adapters (biomech pdf / labs+OCR / adl) behind one interface
  ai/          trajectory analysis: stats-in-code + BAA-covered LLM synthesis
alembic/       migration files (FILES-ONLY: generate + review; a human applies)
```

## Architecture in one paragraph

Each ingestion adapter normalizes its source into `Observation` rows (typed,
timestamped, source-tagged, with provenance + capability-state in JSONB). The
trajectory service computes trend statistics **in code** (slopes, change-points,
reference-range crossings), then the `ai/` layer uses a BAA-covered model only to
*synthesize and explain* over those computed stats — producing an explainable, sourced,
confidence-scored `Trajectory`. Every feature is gated by the capability/toggle model,
enforced server-side. PHI access and toggle changes are audit-logged.

## Run locally

```bash
cd backend
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

cp .env.example .env          # fill in locally; never commit .env

# Postgres via Docker (example):
# docker run --name neuro-pg -e POSTGRES_USER=neuro -e POSTGRES_PASSWORD=neuro \
#   -e POSTGRES_DB=neuropathy -p 5432:5432 -d postgres:16

# Migrations are files-only — generate + review, then apply intentionally:
alembic revision --autogenerate -m "init"    # writes a file; review it
# alembic upgrade head                        # a human runs this

uvicorn app.main:app --reload
# -> http://127.0.0.1:8000  (docs at /docs, health at /healthz)
```

## Guardrails (see repo CLAUDE.md)
- No secrets in the repo; config comes from `.env` / a secrets manager.
- AI/OCR providers must be **BAA-covered** before any PHI flows (ADR-0003).
- Uploaded documents are untrusted input: sandbox parsing; sanitize before AI.
- Every patient-scoped query filters by `patient_id` (and clinic in the clinical version).
