# ADR-0043 — Symptom item-bank + ADA construct mapping (measurement-rigor groundwork)

- **Status:** Accepted (groundwork; deterministic, no behavior change). IRT/CAT and any
  validation claim remain gated on the open decisions below.
- **Date:** 2026-07-18
- **Builds on:** ADR-0034 (NSI, Phase-1 symptom capture), ADR-0006 (research-grade
  Observations), ADR-0011/0016/0041 (non-diagnostic posture). Roadmap Spec 4
  (`docs/product/roadmap-buildout-specs.md`). Evidence: `docs/product/market-position-and-gaps.md`
  (measurement rigor = the #1 product gap), `instrument-licensing-research.md`.

## Context

The market analysis named **measurement rigor** the single biggest product gap: the NSI is
explainable but unvalidated, with the symptom items defined ad-hoc inside the ingestion
adapter. Two cheap, honest groundwork steps move us toward credibility without touching the
computed score or making any clinical claim:

1. **Anchor the symptom items to the ADA screening frame.** The ADA Standards of Care assess
   DPN at diagnosis and at least annually (Rec 12.17), via clinician exam modalities:
   temperature/pinprick (small fiber), 128-Hz tuning-fork vibration (large fiber), and an
   annual 10-g monofilament (Rec 12.18). Mapping our items to those *constructs* gives a
   recognized frame — provided we do not overstate a self-report as an exam.
2. **Lay the IRT/CAT seam** (Spec 4) as a deterministic, uncalibrated stub, so the path to
   Computerized Adaptive Testing (the documented respondent-burden lever) exists without
   claiming precision we don't have.

## Decision

**Introduce a `psychometrics` package as the single source of truth for the symptom items,
carrying honest ADA construct metadata and an uncalibrated administration stub — with zero
change to the computed NSI or the scored Observations.**

- **`app/psychometrics/item_bank.py`** — `ItemBank` of `SymptomItem`s (pain, numbness), each
  with `construct`, `ada_fiber_class`, `ada_modality_related`, `measure_alignment`,
  `polarity`, scale, and an all-None `ItemCalibration`. `is_calibrated` is **False** today.
- **`app/psychometrics/administration.py`** — `FixedOrderSelector` (`is_adaptive=False`) and
  `SumScoreEstimator` (`is_irt=False`, ignores calibration) — the deterministic stub.
- **`app/ingestion/adl.py`** now **derives** its symptom codes, displays, alignment, and
  provenance from the bank. The emitted Observations are **byte-identical** on every scored/
  identity field (code, value, unit, instrument, polarity, scale, `validated_instrument:
  False`); the ADA keys (`construct`, `ada_fiber_class`, `ada_modality_related`,
  `ada_reference`, `patient_reported: True`) are **additive** provenance in `quality`, which
  the NSI never reads — so the score is provably unchanged.

**Honesty guards (enforced by tests):** the bank stays uncalibrated; no item claims a
validated instrument; the stub never claims adaptive/IRT; the bank's polarity matches the
directionality registry and its scale matches the schema's validated max (parity tests).

**The ADA mapping does not overstate.** `ada_modality_related` is explicitly "related to,"
not "equivalent to" — a patient-reported symptom mapped to the fiber construct the ADA exam
assesses, never presented as a monofilament/tuning-fork result. Consistent with ADR-0041: no
clinical/diagnostic claim attaches.

## Consequences

- **A credibility anchor with no risk:** the symptom items now carry a recognized ADA frame
  and a single-source-of-truth definition, with the score and all prior provenance unchanged.
- **The IRT/CAT path exists** behind a seam, gated on `ItemBank.is_calibrated` — CAT becomes a
  new selector/estimator when real calibration data lands, not a rewrite.
- **Nothing overclaims:** the guards make it structurally hard to start asserting validation
  or IRT precision by accident.

## Open decisions (gates — non-code, unchanged by this ADR)

- **Item-bank expansion** (full NTSS-6 vs a de-novo set) — needs clinical + licensing input
  (`instrument-licensing-research.md`; NTSS-6 terms unconfirmed).
- **IRT model choice + real calibration data** — a validation-study output, not inferable.
- **Whether the mapped constructs are validated indicators** — the clinical-evaluation
  question routed by ADR-0041 to qualified professionals. Until then everything here stays
  `validated_instrument: False` and non-diagnostic.

## Alternatives considered

- **Map items directly to the ADA exam modalities (call a numbness report a "monofilament").**
  Rejected — a category error that overstates a self-report as a clinician exam and would
  invite a clinical claim. The construct-level "related to" mapping is the honest form.
- **Build real IRT/CAT now.** Rejected — requires calibration data we don't have; a stub with
  guards is the correct groundwork.
- **Leave the items inline in `adl.py`.** Rejected — the single-source-of-truth bank is what
  lets the ADA metadata and the future item-bank/CAT work attach in one place.
