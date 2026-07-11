# ADR-0003: Product Scope & Data Posture — Ingest, Graph, Analyze (not Measure)

**Date:** 2026-07-11
**Status:** Accepted (owner decision)
**Supersedes:** the open sensor-posture question raised in the BioMech Lab report
review (`docs/requirements/biomech-health/2026-07-11-biomech-lab-report-format.md`).

## Context

BioMech Health **already ships their own patient phone app and clinic app**, and owns
the movement-measurement technology (the wearable-IMU balance/gait system behind
BioMech Lab). Our product does **not** need to — and must not — reproduce that
measurement capability.

The owner defined our product as a layer that:
1. **Ingests** BioMech movement data (V1: their PDF reports; V2: their API/SDK) and
   **graphs** it over time.
2. **Ingests patient-imported lab results.**
3. **Ingests / captures ADL** (Activities of Daily Living / functional-status) data.
4. Uses **AI to analyze ADL + BioMech + Lab data together** to assess whether the
   patient's health is **improving or not** over time.

Both delivery versions still apply (B2C patient-facing + clinical), and full feature
toggling still applies (user-controlled in B2C, clinician-controlled in clinical).

## Decision

**We build the aggregation + visualization + AI-insight layer, not the measurement
instrument.**

- **No phone-as-sensor.** We do not implement balance/gait/vibration measurement.
  (This retires INVENTION CANDIDATEs that assumed we'd measure: haptic VPT self-test,
  phone-derived sway/gait scoring. They belong to BioMech's domain.)
- **Three ingestion sources:** BioMech recordings, patient labs, ADL data.
- **AI health-trajectory analysis** across the three sources is the product's
  differentiating core.

## Where the IP now lives (critical)

The patent goal of this project now rests **entirely on the AI multi-source analysis
layer**, because ingesting and charting data is, by itself, well-trodden and unlikely
to be patentable.

> **INVENTION CANDIDATE (primary):** A method for assessing longitudinal health
> trajectory in peripheral-neuropathy patients by fusing (a) biomechanical movement
> metrics, (b) functional ADL data, and (c) laboratory results into a combined
> "improving / not improving" determination — including how the modalities are
> aligned in time, weighted, and reconciled when they disagree, and how confidence is
> expressed given missing/toggled-off sources.

Honest caveat for counsel (not legal advice): health-trend AI and multi-source patient
dashboards have **extensive prior art**. Novelty must be pinned to something specific
and non-obvious — the *neuropathy-specific fusion method*, a particular
alignment/weighting mechanism, or the toggled-source confidence model — not "AI looks
at health data." A real prior-art search is required before relying on this.

## Consequences

- **Ingestion, not instrumentation, drives the architecture.** Effort moves to: a
  BioMech PDF parser (V1), a lab-import pipeline, an ADL capture mechanism, a unified
  longitudinal data model, and the AI analysis service.
- **Dependency on BioMech's data format.** V1 ingestion parses their report PDFs
  (structure documented in the report-format review). We should request sample PDFs
  (synthetic/de-identified) and, for V2, their API/SDK docs — under the agreement.
- **AI + health data raises two hard constraints, each its own future ADR:**
  - **HIPAA:** any AI/LLM processing patient data needs a BAA-covered service, or
    on-device / de-identified processing. No patient data to a non-BAA AI vendor.
  - **FDA SaMD:** an AI that outputs "your health is improving / declining" leans
    toward interpretation and possibly clinical decision support. Framing, claims, and
    whether a clinician is in the loop determine the regulatory class. Counsel/
    regulatory review required before this ships as anything but clearly-labeled
    wellness trend information.
- **ADL source is unresolved** (self-reported questionnaire vs. sensor-derived vs.
  both) — see open questions; it's an input to Brainstorm #3 and a later ADR.

## Options considered

- **Phone-as-sensor / build our own measurement:** rejected — BioMech owns and ships
  that; duplicating it competes with our own licensee and adds regulatory burden.
- **Ingest + graph only (no AI):** rejected — insufficiently differentiated and not
  patentable; the owner wants the AI analysis.
- **Ingest + graph + AI trajectory analysis across BioMech/Lab/ADL:** chosen — this
  is where the differentiation and the patent surface concentrate.

## Open questions (owner / BioMech)
1. **ADL data source:** validated self-report instrument, sensor/wearable-derived, or
   both? (Some ADL scales are copyrighted — licensing check.)
2. **BioMech ingestion V1:** do we parse their report PDFs, or can their patient app
   export structured data sooner? Can we get synthetic sample PDFs now?
3. **Lab import method for V1:** photo/PDF upload + extraction, manual entry,
   Apple Health / Health Connect lab records, or a lab/portal (FHIR) integration?
4. **AI output audience & authority:** shown to patient, clinician, or both? Is a
   clinician required to be in the loop before a trajectory judgment is surfaced?
5. **AI hosting:** is there a preferred BAA-covered model provider, or should analysis
   run on-device / on de-identified data?
