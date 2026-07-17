# ADR-0038 — Continuous glucose (CGM) via the health bridge

- **Status:** Accepted
- **Date:** 2026-07-17
- **Builds on:** ADR-0035 (phone-base ADL health bridge — HealthKit / Health Connect seam,
  `ingest_wearable` capability, research-grade Observations), ADR-0006 (append-only Observations),
  ADR-0013 (enforced toggles), ADR-0034 (NSI). Relates to the existing HbA1c lab ingestion.

## Context

Glycemic control is a recognized modifiable driver of DPN progression, and HbA1c is already a
Physiologic input to the NSI. Continuous glucose (CGM) adds a far richer, higher-frequency signal.
Two integration paths exist:

- **Path A (this ADR): platform-first.** Apple **HealthKit** and Android **Health Connect** both
  expose a **blood-glucose** data type, and the major CGM apps (Dexcom, FreeStyle Libre) write into
  them. We can read glucose through the **health seam we already built** — no vendor SDK, no
  partnership, no BAA.
- **Path B (deferred): direct vendor APIs/SDKs** (Dexcom Developer API, Abbott LibreView) — gets
  non-platform users and richer/real-time data, but requires developer accounts, partnership terms,
  and likely BAAs. Documented as a future option, not built here.

## Decision

**Ingest blood glucose through the existing health bridge as a research-grade Observation** — the
same seam, capability, endpoint, and provenance discipline as the ADR-0035 wearable metrics.

- **Metric.** Add `blood_glucose` to the health-bridge metric catalog, unit **mg/dL** (canonical).
  The native seam converts HealthKit `bloodGlucose` / Health Connect `BloodGlucose` samples to
  mg/dL **before** sending (mmol/L × 18.0182), consistent with the "metric determines the unit,
  the client never names a unit" rule (ADR-0035). Backend applies a plausibility range and skips
  outliers with a warning (never coerces), like every other ingested metric.
- **Directionality.** Register `blood_glucose` as **`in_range_is_better`** (a high or low reading
  is worse) with a plain-language label ("blood sugar"), mirrored in the frontend `signalMeta`.
- **NSI: not folded into the Index in v1.** A single glucose reading is not a validated NSI input
  the way HbA1c is. `blood_glucose` is a **tracked signal** — it graphs, trends, appears in the
  Records/clinician views, and lands in the warehouse — but is **excluded from the composite**
  (asserted by test, same rule that excludes `adl_daily_score`). Deriving **time-in-range / mean /
  variability** and folding a validated glycemic summary into the Physiologic tier is the defined
  **follow-up**, pending clinical sign-off on thresholds and weighting.
- **Consent + audit.** Gated by the existing health-bridge opt-in (`ingest_wearable`, default off);
  glucose is PHI, so the audit stays counts-only (never a value). Whether glucose warrants its own
  dedicated capability separate from mobility is an open decision (v1 reuses the health-bridge gate).

## The hard guardrail

**Non-diagnostic. No real-time glucose alarms and no dosing guidance — ever.** Real-time
alerting and insulin-dosing are the CGM device's own **regulated** functions; replicating them
would make this a far higher-risk device and is dangerous if wrong. We use glucose as **trend +
context** for the Physiologic picture and glycemic-control education, not as an alerting device.

## Consequences

- CGM users whose app writes to Apple Health / Health Connect get glucose into the warehouse and
  the clinician full-picture view with near-zero new surface (reuses the ADR-0035 machinery).
- Not yet done: derived time-in-range/mean/variability, NSI Physiologic inclusion, a dedicated
  glucose consent toggle, and any direct Dexcom/Abbott SDK (Path B).

## Honesty invariants

Synthetic data only in tests; PHI-free audit (counts, never values); displays come only from the
closed registry; unit is canonicalized at the edge and validated at intake; non-diagnostic, with
no alarms or dosing. Path B partnership/BAA realities are documented, not assumed.
