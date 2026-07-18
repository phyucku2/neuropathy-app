# ADR-0044 — Clinician feedback loop: alerts + PRO-to-EHR write-back (spec)

- **Status:** Proposed (spec — not built). Both phases are gated (below); nothing here ships
  until its gate clears.
- **Date:** 2026-07-18
- **Builds on:** ADR-0012/0016 (clinician surface, non-diagnostic note), ADR-0008/0009/0028
  (SMART-on-FHIR patient pull), ADR-0013/0020 (capabilities, consent), ADR-0041 (FDA
  device-status framework), `docs/product/market-position-and-gaps.md`.

## Context

The market analysis found the **outbound clinician loop** to be a table-stakes gap and a
demonstrated driver of both adoption and sustained engagement for 60+ patients: clinicians
engaging with patient-generated data motivates patients, and patients often won't adopt
without a physician recommendation. Today we **pull** EMR labs inbound (ADR-0028) and show a
clinician a consent-gated panel (ADR-0012), but we do **not**:

1. **push** patient-reported outcomes back into the EHR for in-encounter viewing (the
   demonstrated SMART-on-FHIR PRO-integration pattern), nor
2. surface **alerts/escalation** when a trajectory declines or data goes stale.

Both are attractive — and both sit close to the interpretive/decision-support line that
ADR-0041 guards. An "alert to escalate" on a computed decline is exactly the kind of output
that could be read as clinical decision support, and PRO write-back is a large,
vendor-dependent capability. So this ADR **specs** the loop and sets the gates rather than
building it blind.

## Decision (phased spec)

**Phase A — In-app clinician signals (buildable within our architecture, gated on ADR-0041).**
A consent-gated, **non-diagnostic** clinician-panel surface that flags, for patients who share
with the clinic: (a) a **data-gap / staleness** signal (no check-ins or no fresh data in N
days — a *data-completeness* fact, not a clinical judgment), and optionally (b) a
**trajectory-direction** indicator already computed deterministically (ADR-0016). No new
interpretation is created; it re-presents existing deterministic output with the
non-diagnostic note co-located. **Gate:** because a clinician-facing "escalation" edges toward
decision support, Phase A ships only after the ADR-0041 consultant opinion confirms it stays
non-device (or is scoped to pure data-completeness, which is safely non-interpretive). Build
data-gap signalling first (clearly non-interpretive); hold direction-based "alerts" for the
opinion.

**Phase B — PRO-to-EHR write-back (architecturally significant; deferred to build).** Push
patient-reported outcomes to the EHR as FHIR `Observation`/`QuestionnaireResponse` via
SMART-on-FHIR **write** scopes (e.g. `patient/Observation.write`), so a clinician sees them in
their own workflow. This requires: separate **write** app-registration with each vendor
(distinct from the read scopes we register today, ADR-0009), vendor write support (uneven
across Epic/Oracle/etc.), a new backend write path with its own provenance/audit, and clear
labelling that the data is patient-reported and non-diagnostic. **Gate:** ADR-0041 posture +
per-vendor write availability + a dedicated design ADR. Not built here.

**Not in scope:** care-team messaging/chat (a separate product surface with its own privacy/
retention design) — noted as a future item, not specced here.

## Consequences

- **The loop is governed, not ad-hoc:** the table-stakes gap is acknowledged with a safe,
  phased path that respects the FDA framework instead of shipping an "alert" that could forfeit
  the non-device posture.
- **Phase A's data-gap signal is the safe first brick** — a completeness fact (no PHI
  interpretation) that already improves the clinician loop and 60+ retention, and it reuses
  the consent gate (`share_with_clinic`) and the clinician panel we already have.
- **Phase B is correctly deferred** — write-back is a real capability but vendor-dependent and
  claim-sensitive; building it blind would be premature.

## Open decisions (gates)

- **ADR-0041 opinion** on whether a clinician-facing trajectory alert is non-device CDS or
  crosses into device territory (drives what Phase A may include).
- **Per-vendor FHIR write support + write-scope registration** terms (Epic/Oracle/…).
- **Provenance/labelling** for written-back PROs so the EHR record can't be mistaken for a
  validated/clinical measurement.
- **Messaging** as a separate surface — deferred.

## Alternatives considered

- **Build trajectory alerts now.** Rejected — an escalation on a computed decline is an
  ADR-0041 device-path trigger; it needs the consultant opinion first. Data-gap signalling is
  the non-interpretive first step.
- **Build PRO write-back now.** Rejected — vendor-dependent, needs write registration + a new
  backend + claim-safe labelling; spec first.
- **Do nothing (status quo inbound-only).** Rejected — the clinician loop is a validated
  adoption/retention driver; leaving it unaddressed cedes a table-stakes capability.
