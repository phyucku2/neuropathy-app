# ADR-0007: Labs Modeled on FHIR R4 · BioMech Is a Separate Module

**Date:** 2026-07-11
**Status:** Accepted (owner decision)
**Clarifies:** ADR-0006 (data integrity) — its target for *now* is lab data via FHIR.

## Context

The "research grade / standards" direction refers, concretely, to **FHIR for labs**.
Lab results are the data source we model to a recognized clinical standard now.
**BioMech data is a separate module** to be built when we get there — it is not modeled
in the core data schema at this stage.

## Decision

1. **Labs are modeled on HL7 FHIR R4 `Observation` semantics:**
   - `code` is a LOINC-coded concept (`code_system = "LOINC"`).
   - Quantities use **UCUM** units (`unit_system = "UCUM"`).
   - `effective_at` ↔ FHIR `effectiveDateTime`; `recorded_at` ↔ FHIR `issued`.
   - `status` mirrors FHIR `Observation.status`
     (`preliminary | final | amended | corrected | entered-in-error`).
   - Reference range and interpretation are captured for each result.
   - The internal model is FHIR-*aligned*; full FHIR resource import/export (parsing
     external `Observation` JSON, exposing a FHIR endpoint) is a follow-up increment.

2. **BioMech is a separate module, deferred.** The core `SourceType` no longer lists
   `biomech`; the BioMech module will add its own ingestion and representation when
   built. Product vision (brainstorms/mockups) still shows BioMech as a source — this
   ADR scopes only what the **core data model builds now**.

3. **ADL** (patient-reported functional status) remains in the core as a
   patient-reported source; it is not a lab and is not FHIR-lab-shaped.

## Consequences

- `SourceType` = `{ lab, adl }` for now (BioMech added later, as its own module).
- A FHIR-aligned **lab input schema** (`app/schemas/lab.py`) validates lab results on
  intake: LOINC code required, UCUM unit for quantities, effective time, status,
  reference range, interpretation.
- The integrity work from ADR-0006 (immutable/append-only, corrections-as-new-records,
  dual timestamps, provenance) stands — it is exactly how FHIR treats an `Observation`
  lifecycle, so it applies directly to labs.
- When the BioMech module lands, it plugs into the same unified `Observation` store (or
  its own, TBD in that module's ADR) without reworking labs.

## Options considered

- **Custom lab schema:** rejected — labs have a universal standard (FHIR + LOINC +
  UCUM); using it makes data poolable, interoperable, and clinician-trusted.
- **Build BioMech into the core now:** rejected per owner — BioMech is a separate
  module; modeling it now would couple unrelated concerns prematurely.
- **FHIR R4 for labs + BioMech as a later module:** chosen.
