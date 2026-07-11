# Product Requirements — v1.1 (owner clarification)

**Received:** 2026-07-11
**Supersedes:** amends v1 (`2026-07-11-product-requirements-v1.md`) where they conflict.
**Decisions recorded in:** ADR-0003 (scope/posture), ADR-0002 (brand, colors approved).

## What changed from v1

1. **BioMech data = ingest & graph only.** BioMech Health already ships their own
   patient app and clinic app and owns the measurement. We do **not** measure; we
   **ingest** their movement data and **graph** it. (V1 ingest = their PDF reports;
   V2 = their API/SDK.)
2. **Patient can bring in their own labs.** Lab results are a patient-imported data
   source.
3. **AI analysis across three modalities.** Use AI to analyze **ADL + BioMech + Lab**
   data together and review whether the patient's health is **improving or not**.
4. **Brand colors approved** ("colors look good").

## Consolidated v1.1 product definition

A patient-fronting (B2C) and clinical health app that:
- **Ingests** three data sources — BioMech movement recordings, patient-imported labs,
  and ADL/functional data — into one longitudinal record.
- **Graphs** each source's trends over time.
- **Analyzes** the combined picture with AI to assess health trajectory
  (improving / stable / declining) and surface what's driving it.
- Ships as **B2C** (patient toggles every feature) and **clinical** (clinician toggles
  every feature; data flows to the servicing clinic).

## Still-open clarifications (carried into Brainstorm #3 as assumptions)
- ADL source: validated self-report vs. sensor-derived vs. both. *(Assume both.)*
- Lab import mechanism for V1: upload+extract vs. manual vs. Health-record/FHIR.
  *(Assume upload-a-PDF/photo + extraction, with manual fallback, for V1.)*
- BioMech V1 feed: parse report PDFs vs. earlier structured export. *(Assume PDF parse.)*
- AI output audience/authority: patient, clinician, or both; clinician-in-the-loop?
  *(Assume both, with clinician-in-the-loop required before a trajectory judgment is
  presented as clinical, and wellness-framed trends for B2C.)*
- AI hosting: BAA-covered provider vs. on-device/de-identified. *(Assume BAA-covered.)*
