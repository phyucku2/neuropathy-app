# ADR-0006: Research-Grade Data Collection

**Date:** 2026-07-11
**Status:** Accepted (owner decision)

## Context

Data collected by this product must be **research grade** — usable as evidence in
validation studies, defensible to regulators, and reproducible. That raises the bar on
how every datum is captured, stored, and corrected, well beyond "good enough to display
a chart." It also directly serves the product: the trajectory analysis is only as
trustworthy as its inputs.

## Decision

Adopt recognized clinical-research data standards for all collected data. The concrete
standard lives in [`docs/engineering/data-standards.md`](../engineering/data-standards.md);
the load-bearing commitments:

- **ALCOA+ integrity.** Every datum is Attributable, Legible, Contemporaneous,
  Original, Accurate — plus Complete, Consistent, Enduring, Available.
- **Immutable, append-only.** Values are never overwritten or hard-deleted. A
  correction is a **new record** that supersedes the prior one; the original endures.
  Lifecycle is tracked with a FHIR-style status (`preliminary → final → amended /
  corrected / entered_in_error`). Erroneous data is flagged, never erased.
- **Full provenance on every datum.** Origin (device-measured / document-imported /
  patient-reported / derived), source system/device, collection method, instrument or
  protocol **version**, who/what recorded it and their role, and — where relevant —
  extraction confidence, calibration state, and a human-confirmed flag.
- **Two timestamps, always.** `effective_at` (when the observation is clinically about)
  and `recorded_at` (when it entered the system — contemporaneous capture). All UTC,
  timezone-aware.
- **Standardized coding.** Labs → **LOINC**; units → **UCUM**; clinical terms →
  SNOMED CT where applicable. Coding system is stored alongside every code/unit so data
  is unambiguous and poolable.
- **21 CFR Part 11 alignment** for electronic records/signatures where research/e-consent
  applies: audit trail of record changes, attributable actions, secure retention.
- **Reproducibility.** Versioned data dictionary/codebook; dataset snapshots are
  versioned; de-identified export supported for analysis/registry without exposing PHI.
- **Consent for research use** is explicit, versioned, and separate from care use;
  research export honors the consent scope.

## Consequences

- **Data model:** `Observation` gains provenance + integrity + coding fields (origin,
  code_system, unit_system, value_text, status, `revises_id`, recorded_at,
  collected_by_role, quality JSONB). Corrections link via `revises_id`; the analytical
  view excludes `entered_in_error` while retaining it for the record.
- **Ingestion adapters** must populate provenance (device/method/version, extraction
  confidence, human-confirmed) — not optional metadata but part of the record.
- **Trajectory analysis** consumes only the current, non-errored records and can state
  data provenance/quality in its confidence (ties to the ADR-0003 confidence model).
- **Audit** already logs PHI access + config changes; research-grade adds record-change
  history (who corrected what, when, why).
- More fields and stricter capture rules — accepted as the cost of evidence-grade data.

## Options considered

- **Display-grade capture (store the value, allow edits):** rejected — un-auditable,
  not reproducible, useless for validation or regulatory evidence.
- **Research-grade (ALCOA+, immutable, provenanced, coded):** chosen — matches the
  product's validation goals and the owner's directive.
