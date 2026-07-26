# ADR-0049 — The daily neuropathy instrument: symptoms + function as one 5-item core

- **Status:** Accepted (product decision; clinical/psychometric validation still pending —
  the instrument stays non-diagnostic and illustratively weighted until validated).
- **Date:** 2026-07-26
- **Amends:** ADR-0034 (symptom check-in — Phase 1 shipped symptoms as an OPT-IN, default-OFF
  toggle). This ADR makes them part of the default daily core.
- **Builds on:** ADR-0006 (append-only Observations), ADR-0013 (enforced capability toggles),
  ADR-0016 (non-diagnostic directionality), the NSI composite (`app/trajectory/composite.py`),
  and the measurement-rigor groundwork (ADA construct mapping + IRT/CAT).

## Context

The daily patient check-in has two parts today:

- **Function (ADL)** — 3 items (Walking, Stairs, Balance confidence), 0–4, default **ON**.
- **Symptoms** — 2 items (Pain, Numbness/paresthesia), 0–10 NRS-aligned, default **OFF**
  (ADR-0034 Phase 1 shipped them opt-in).

Both are captured by the same `POST /adl` submission and both feed the Neuropathy Status Index
(symptoms → symptom domain; ADL → function domain, alongside episodic device-grade BioMech and
periodic HbA1c). BioMech and labs already fold into the NSI at their own cadences and are
untouched by this decision.

The problem: **symptoms (pain, numbness/paresthesia) are the *core* construct a neuropathy
patient-reported measure exists to capture** — they are the spine of every validated DPN
instrument (NTSS-6, MNSI, NPSI, DN4/painDETECT). Shipping them default-OFF means a fresh
patient's daily protocol is *function-only*, and the symptom domain of the NSI is empty until
they opt in. For an instrument that claims to track neuropathy *status*, that inverts the
priority: the functional complement is on, the symptom spine is off.

## Decision

**Make the daily protocol one unified 5-item instrument — Pain, Numbness, Walking, Stairs,
Balance confidence — with symptoms ON by default.** Concretely: flip the `ingest_symptoms`
capability default from `False` to `True`.

We keep symptoms as a **separable, patient-controlled toggle** rather than merging them into the
base check-in. Two reasons:

1. **Autonomy (ADR-0013).** A daily pain/numbness prompt is a heavier, more personal ask than a
   function question. A patient who does not want to be asked about pain every day can turn the
   symptom items off in Sources and keep the function check-in. Consent is the default-plus-
   opt-out posture, not a forced field.
2. **Separable provenance.** The symptom items (0–10, worse-is-higher) and the function items
   (0–4, better-is-higher) are different scales feeding different NSI domains; keeping the toggle
   distinct keeps that boundary clean and lets analysis/validation reason about them separately.

Onboarding discloses the daily instrument (what is asked, and that symptoms can be turned off),
so the default-on is informed, not silent.

## Consequences

- **The default daily protocol becomes the full 5-item instrument** — the symptom spine + the
  functional complement — so a new patient's NSI carries the symptom domain from day one.
- **BioMech + labs are unchanged** — they remain the episodic device-grade and periodic
  physiologic inputs to the NSI; this decision only concerns the *daily patient ask*.
- **Reversible per patient** — the `ingest_symptoms` toggle stays; a patient can return to a
  function-only daily check-in at any time (409-enforced server-side, ADR-0013).
- **Honest framing preserved** — still non-diagnostic; the composite weighting is illustrative
  and physician-signed pending validation (ADR-0016/0034). Nothing here asserts clinical-grade
  measurement.
- **Not a scale change** — the items, codes, and scoring are unchanged from ADR-0034; only the
  default exposure changes. The item bank and any future CAT/IRT work (measurement-rigor
  groundwork) build on the same codes.

## Alternatives considered

- **Merge symptoms into the base `ingest_adl` capability (one indivisible instrument).** Rejected:
  removes the patient's ability to decline daily symptom prompts while keeping function tracking,
  and blurs the two scales/domains. Default-on-with-opt-out achieves the same "symptoms are core"
  outcome while respecting autonomy.
- **Leave symptoms opt-in (status quo).** Rejected: makes the neuropathy PRO spine optional and
  leaves the NSI symptom domain empty for most patients — backwards for a status instrument.
- **Symptoms-only daily, ADL weekly.** Rejected for now: the daily function signal is cheap and
  valuable (falls/mobility trajectory), and dropping it daily loses resolution; revisit if daily
  burden proves too high in real use.
