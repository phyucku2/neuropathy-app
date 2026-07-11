# ADR-0004: Backend Stack

**Date:** 2026-07-11
**Status:** Accepted (proposed by build team; easy to revisit while it's a skeleton)

## Context

The backend must: ingest and parse documents (BioMech report PDFs, lab PDFs/photos),
run OCR/extraction, orchestrate an AI trajectory analysis over a unified longitudinal
health record, serve two clients (B2C patient app + clinical app), enforce a
capability/toggle authorization model, and hold PHI under a HIPAA-grade posture with
per-clinic multi-tenancy. Workloads are **I/O-bound** (outbound calls to OCR/LLM
providers, document handling) more than CPU-bound.

## Decision

**Python 3.12 · FastAPI (async) · PostgreSQL · SQLAlchemy 2.0 (async) · Alembic ·
Pydantic v2.**

- **FastAPI, async** — first-class async for concurrent outbound calls (LLM, OCR),
  automatic OpenAPI docs for the mobile teams, dependency-injection that maps cleanly
  onto our per-request auth + capability checks.
- **Python** — strongest ecosystem for the product's core: PDF parsing, OCR, and
  LLM/AI orchestration all live here. Keeps the differentiating work in one language.
- **PostgreSQL** — reliable relational core for a longitudinal health record, with
  JSONB for heterogeneous source payloads (lab panels, BioMech metric sets) and strong
  support for the time-based queries trend analysis needs.
- **SQLAlchemy 2.0 async + Alembic** — mature ORM + migrations. **Migrations are
  files-only in this repo**: generate and review migration files; a human applies them.
- **Pydantic v2** — strict schema validation at the API boundary; important for health
  data integrity and for validating extracted lab values before they're trusted.

## Structure (vertical, by concern)

```
backend/
  app/
    core/        # config, security, settings
    db/          # engine, session, declarative base
    models/      # SQLAlchemy models (unified record, capability, audit, ...)
    schemas/     # Pydantic request/response models
    api/routes/  # thin HTTP routers -> services
    services/    # business logic: ingestion, analysis, capabilities, audit
    ingestion/   # source parsers (biomech PDF, lab extract, adl) behind one interface
    ai/          # trajectory-analysis orchestration (stats-in-code + LLM synthesis)
  alembic/       # migration files (files-only)
```

Design intent (from Brainstorm #3): a **unified longitudinal record** at the center;
ingestion adapters normalize each source into it; the AI layer computes trend stats in
code and uses the model only to synthesize/explain over those stats.

## Consequences

- Mobile stack is decided separately (platform ADR still open). The backend is
  client-agnostic (JSON/OpenAPI), so React Native, native, or Flutter all fit.
- AI/OCR provider choices are their own ADRs and must be **BAA-covered** for PHI
  (ADR-0003 constraint). Services sit behind interfaces so providers are swappable.
- Async SQLAlchemy has a learning curve; acceptable for the I/O-bound profile.

## Options considered

- **Node/TypeScript (NestJS):** attractive for one language across a React Native app;
  rejected as the primary because the document-parsing/OCR/AI ecosystem is weaker than
  Python's, and that's exactly our core.
- **Django + DRF:** batteries-included and solid for admin, but heavier and its sync
  default fits our outbound-I/O profile less well than async FastAPI.
- **Go:** great concurrency/perf, but the AI/document ecosystem is thin; not worth it
  for an I/O-bound, AI-centric backend.
- **Python + async FastAPI + Postgres:** chosen — best fit for the product's core.

> Note: FastAPI/Postgres is a mainstream, public-domain stack choice driven by these
> requirements — not adapted from any prior project (clean-room §1).
