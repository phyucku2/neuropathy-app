# Data Standards — Research Grade

The concrete standard behind ADR-0006. Binding on all data collection (CLAUDE.md §5, §7).
Goal: every datum is defensible as research evidence — traceable, reproducible, and
integrity-preserving.

> **Scope now (ADR-0007):** the immediate application is **lab data, modeled on
> HL7 FHIR R4** (`Observation`, LOINC codes, UCUM units). **ADL** is a patient-reported
> source. **BioMech is a separate module** built later and is not in the core data
> model yet. The integrity principles below apply to every source we do collect.

## ALCOA+ (the integrity backbone)
| Principle | What it means here |
|---|---|
| **Attributable** | Every datum records who/what produced it and their role. |
| **Legible** | Structured, coded, human-readable; no opaque blobs as the source of truth. |
| **Contemporaneous** | `recorded_at` captured at collection time, not backfilled. |
| **Original** | The first-captured value is preserved; corrections never overwrite it. |
| **Accurate** | Validated at the boundary; extracted values human-confirmed before trust. |
| **Complete** | Nothing silently dropped; missing data is represented, not omitted. |
| **Consistent** | Standard codes/units; consistent timestamps (UTC). |
| **Enduring** | Append-only storage; errored data flagged, retained, never deleted. |
| **Available** | Retrievable and exportable for the life of the record. |

## Record lifecycle (immutability)
- Status follows FHIR `Observation.status`: `preliminary → final`, then `amended`
  (new info), `corrected` (fixing an error), or `entered_in_error` (should not have
  existed — retained but excluded from analysis).
- **Corrections are new rows** that point to the record they supersede (`revises_id`).
  The superseded row stays; the chain is the change history.
- Value/quantity fields are **never mutated**. Only lifecycle status transitions occur,
  and each is audit-logged (who/when/why).

## Provenance (required on every Observation)
- **Origin class:** `device_measured` | `document_imported` | `patient_reported` |
  `derived`.
- **Source detail:** source system/device, collection method, instrument/protocol
  **version** (so a result is reproducible against the exact method used).
- **Attribution:** recording actor + role.
- **Quality:** extraction confidence (for OCR'd values), calibration state, and a
  `human_confirmed` flag. A lab value is not "final" until a human confirms the
  extracted number (ADR-0003 / lab-import flow).

## Timestamps
- `effective_at` — when the observation is clinically about.
- `recorded_at` — when it entered the system (contemporaneous).
- Both timezone-aware UTC; never naive local time.

## Coding & units
- Labs → **LOINC**; units → **UCUM**; clinical concepts → **SNOMED CT** where useful.
- Store the **code system** with every code and unit (`code_system`, `unit_system`) so
  data is unambiguous and poolable across sources.
- Normalize units on ingtake where a canonical unit exists (enables valid trending).

## Regulated records & consent (when research/e-consent applies)
- **21 CFR Part 11**: audit trail of record changes, attributable and time-stamped
  actions, secure and durable retention; e-signatures where used.
- **Research consent** is explicit, **versioned**, and distinct from care-use consent;
  export/use honors the consented scope.

## Reproducibility
- **Data dictionary / codebook** is versioned in-repo and kept in sync with the schema.
- **Dataset snapshots** are versioned; an analysis references the snapshot + code
  version that produced it.
- **De-identified export** (Safe Harbor / expert-determination as applicable) supports
  analysis and registry use without exposing PHI.

## Enforcement
- Schema carries the provenance/integrity/coding fields; ingestion adapters must
  populate them (a datum without provenance is a bug, not a warning).
- Analytical queries select **current, non-errored** records only.
- Integrity rules that can be unit-tested are (see `app/services/observation.py`).
