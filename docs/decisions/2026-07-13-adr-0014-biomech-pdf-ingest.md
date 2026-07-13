# ADR-0014: BioMech PDF Ingest Module (V1) — Text-Layer Parsing Into Observations

**Date:** 2026-07-13
**Status:** Accepted
**Builds on:** ADR-0006 (research-grade data), ADR-0007 (BioMech is a separate module;
core `SourceType` deferred it), ADR-0011 (injection posture, closed-set coding),
ADR-0013 (capability enforcement seam).

## Context

BioMech Health runs their own phone and clinic apps. Our product **ingests and graphs**
their data — nothing more. V1 ingests the balance and gait **assessment report PDFs**
their lab portal exports: digitally generated documents with a real text layer (overall
balance score, sway velocity, sway area; gait speed, cadence, step length, step-time
symmetry). ADR-0007 deliberately kept `SourceType.biomech` out of the core schema until
this module landed; now it lands, as "a separate module by design" (owner's words),
self-contained under `backend/app/biomech/`. The V2 API/SDK path is out of scope
(Deferred, roadmap).

The open questions: how to read the PDF safely, how to turn free-form document text into
research-grade coded rows without inventing data or opening an injection surface, and how
to add a new `SourceType` enum value to a live Postgres column.

## Decision

1. **Text-layer PDF only — no OCR in V1.** BioMech's exports carry a text layer, so we
   extract that text (`pypdf`, BSD-3-Clause) and never rasterize, render, or execute
   anything in the document (no JavaScript, no external fetches). The extractor guards
   hard: size cap and page cap (settings-driven, ~10 MB / 30 pages), magic-byte check,
   and every `pypdf` failure caught and re-raised as a typed `BiomechPdfError` the route
   maps to **422** — a bad upload is a client error, never a 500. Scanned/image PDFs
   yield no text and simply import nothing; OCR is a documented later increment, not a
   V1 dependency.
2. **Closed metric registry.** `app/biomech/parser.py` defines the exact set of metrics
   V1 understands — each with a curated display, unit, valid range, and polarity. Only
   these codes are captured; **unknown lines are ignored and document free text never
   becomes a display label or a code** (ADR-0011 injection posture). Displays come only
   from the registry, exactly as lab displays and ADL displays do. The polarities mirror
   the trajectory directionality registry, and a unit test asserts the two never drift.
3. **Defensive parsing, never fabricate.** A non-numeric or out-of-range value is
   **skipped with a per-metric warning** (returned to the uploader in the response, so
   they see exactly what happened), never coerced or invented. Empty or unrecognizable
   text yields a report with zero metrics and warnings — not an exception. A missing
   report kind or assessment date is a warning, and without a date nothing is imported
   (an Observation must have an `effective_at`).
4. **`document_imported` provenance.** Every row is `source=biomech`,
   `origin=DataOrigin.document_imported` — the value was **extracted from an imported
   document**, not measured by an instrument on our side. `device_measured` is reserved
   for the V2 API/SDK path where BioMech's system reports the measurement directly.
   `quality` records `{"source_system": "BioMech", "extraction": "pdf_text",
   "report_kind": ...}` (plus the device/source line as provenance when present, never as
   a label). `effective_at` is the report's assessment datetime (naive → UTC, like labs);
   status is `final`.
5. **Content-identity idempotency.** The import key is the report's content identity
   (report kind + assessment datetime + code + value + unit), mirroring `lab_import_key`,
   so re-uploading the same report is skipped, not duplicated — one clinical fact, one
   analyzable row.
6. **The enum migration is one-way.** Migration `0003` adds `biomech` to the Postgres
   `source_type` enum. `ALTER TYPE ... ADD VALUE` cannot run inside a transaction, so it
   runs in alembic's `autocommit_block`; `IF NOT EXISTS` makes a partial or repeated
   apply safe. **Downgrade is a deliberate no-op:** Postgres has no safe `DROP VALUE`, and
   removing the value would mean recreating the type without it and rewriting every
   `observation.source` — a data-loss risk on an append-only, research-grade store. An
   unused enum value is harmless, so it stays (refuse-or-noop decision: noop, documented
   here).
7. **Capability-gated, audited.** The upload route (`POST /biomech/reports`) requires
   `PatientUserDep` and `require_capability('ingest_biomech')` (new registry key,
   `default=True`, `enforced=True` — the route is its consumer; off ⇒ 409). The PHI write
   is audit-logged with **counts + report kind only, never a value** (CLAUDE.md §5;
   warnings can carry parsed numbers, so only their count is audited). Uploaded rows flow
   into `GET /observations` and the trajectory automatically (`source='biomech'`), so the
   engine produces sourced signals and plain-language summaries ("balance up 8 over 30
   days") with no change to engine math.

## Consequences

- New self-contained module `app/biomech/` (`pdf`, `parser`, `ingest`), one route
  (`app/api/routes/biomech.py`), one response schema, one dependency (`pypdf`), one
  capability key, one migration (`0003`). Directionality gains seven BioMech codes +
  friendly labels; the trajectory engine gains a BioMech source-gap message.
- Migration/model parity holds: the model enum (`lab`/`adl`/`biomech`) and the migrated
  database agree; the integration autogenerate-parity test stays green.
- Idempotent, provenance-complete BioMech rows are now first-class in every existing
  read surface (observations list, trajectory, clinician cross-source view) with no
  changes to those surfaces.
- V1 cannot read scanned/image-only reports; if BioMech ever exports those, OCR is a
  scoped follow-up (async job, never in the request path — standards.md).

## Options considered

- **OCR now:** rejected for V1 — BioMech's exports have a text layer, so OCR adds a
  provider, a BAA surface, latency, and an accuracy/confirmation problem we don't need
  yet. Documented as a later increment behind the same typed-error boundary.
- **Free-form metric capture (grab every `label: value` line):** rejected — it would let
  document free text become a coded signal and a display label (injection surface,
  ADR-0011) and would break research-grade coding (uncontrolled vocabulary). A closed
  registry keeps coding auditable and the label surface sanitized.
- **`device_measured` provenance for BioMech rows:** rejected for V1 — the value came
  from a document we parsed, not a device we read; `device_measured` is reserved for the
  V2 API/SDK path so provenance stays honest (ALCOA: Attributable).
- **Reversible enum downgrade (recreate the type without `biomech`):** rejected — it
  rewrites every observation row and risks data loss on an append-only store; a no-op
  downgrade with an unused value is the safe, standard Postgres posture.
- **Building BioMech into the core schema (vs. a separate module):** already rejected by
  the owner in ADR-0007; this ADR honors that — the module plugs into the shared
  `Observation` store but owns its own ingest, registry, and route.
