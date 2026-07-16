# The Neuropathy Status Index
### A multimodal protocol for measuring diabetic peripheral neuropathy continuously and objectively in daily life

**Prepared for:** Frank Fornari, PhD — CEO and Founder, BioMech Health
**Prepared by:** Advanced Health and Wellness Group
**Date:** July 2026 · **Relationship:** IP owner (AHWG); BioMech Health, licensee
**Status:** White paper — Confidential

> **Status disclosure.** This paper describes a **non-diagnostic v1** protocol validated
> against **synthetic data only**. It is **not** FDA-cleared, **not** clinically validated,
> and produces **no** diagnosis. Empirical claims were produced by a multi-source
> verification process; claims with strong supporting evidence are marked **verified**, and
> claims that are promising but unverified are **flagged** as such. This document is not
> clinical or regulatory advice — final scientific and regulatory sign-off rests with
> qualified experts.

**Purpose, in one line.** We have **built** a working, non-diagnostic v1 of a continuous,
objective, multimodal neuropathy measure — the Neuropathy Status Index — and this paper
explains **what we built, why it is needed, the evidence it rests on, and why it is now
ready to be tested** in a real diabetic-neuropathy population.

## 1. Executive summary

Diabetic peripheral neuropathy (DPN) is one of the most consequential and least
well-measured complications of diabetes. Current assessment relies on **siloed, episodic,
single-modality** instruments — a questionnaire, a clinic exam, or a quality-of-life survey,
each administered at a single point in time. Our review of the literature identified **no
longitudinal, multimodal composite** that combines patient-reported symptoms, objective gait
and balance, and lab values into one score that tracks a patient over time. This gap defines
the opportunity.

We have built the **Neuropathy Status Index (NSI)**: a composite 0–100 measure from four
signal streams, updated daily, presented with an explicit confidence indicator, and built to
a research-grade data standard from the first record. It runs **alongside BioMech's clinical
platform** rather than competing with it:

- **BioMech provides the clinical tier:** device-grade daily gait and balance (RKM).
- **Our app provides the real-world tier:** passive phone and watch mobility, plus the
  composite index, the patient-facing experience, and the longitudinal record.
- Together these produce a daily, consented, multimodal, longitudinal record of neuropathy —
  the substrate a validated index is built on.

The near-term methods rest on **established measurement science** (adaptive testing and item
response theory to reduce burden; data-driven scoring). The longer-term method, multimodal
machine-learning fusion, is **promising but not yet validated**, and we treat it that way.
The result is a protocol that is **strong on design and explicit about what remains
unvalidated** — built, running on synthetic data, and ready to be tested against real
patients.

## 2. The need: neuropathy is under-measured

- **Human and economic stakes.** Peripheral neuropathy drives falls, mobility decline, and
  loss of independence in an aging population — the same population and fall-risk economics
  BioMech already targets.
- **Measurement is fragmented** <sub>(verified)</sub>. A 2025 systematic review of 184 DSPN
  trials found consistent outcome domains (pain, nervous-system symptoms, physical function,
  quality of life) but severe instrument heterogeneity: 32 different nervous-system tools and
  35 distinct physical-function tools. A 2015 review concluded there is still no gold-standard
  DPN symptom measure.
- **Established instruments are siloed and episodic** <sub>(verified)</sub>. NTSS-6 (sensory
  symptoms, a clinician-reported measure; a separately validated self-administered version,
  NTSS-6-SA, exists), Norfolk QOL-DN (a fiber-specific quality-of-life measure), the mTCNS and
  UENS (clinician exams), and the 10-g monofilament and vibration tests are each validated,
  but each captures one construct at a single visit. None is continuous, and none is
  multimodal.

Neuropathy progresses as a **trajectory**. Measuring it with disconnected snapshots is the
core problem the NSI is designed to solve.

## 3. The protocol: the Neuropathy Status Index

A deterministic, explainable, non-diagnostic composite that combines four streams into one
0–100 score (higher is better), recomputed continuously and shown with a confidence level:

| Domain | Signal | Source and cadence | Basis |
|---|---|---|---|
| **Symptoms** | Pain and numbness / paresthesia | Patient self-report, daily | NRS / NTSS-6-SA-aligned (PRO) |
| **Function — clinical** | Gait and balance | BioMech, daily (device-grade) | IMU gait, mCTSIB balance |
| **Function — real-world** | Everyday mobility | Phone (base) plus watch (optional) | Apple Health / Health Connect |
| **Physiologic** | HbA1c and related labs | EMR via SMART-on-FHIR | LOINC |

**Three properties make it distinctive:**

1. **Multimodal fusion into one score**, which fills the documented gap.
2. **Two-tier function measurement.** The index tracks whether a patient improves both in the
   clinic test (BioMech) and in daily life (phone and watch), with the consumer-grade signal
   down-weighted for fidelity so it is never treated as device-grade. Demonstrating
   improvement in both the clinic and daily living supports the value-based-care and payer
   argument.
3. **A daily curve rather than a snapshot**, which is what supports trend detection,
   responsiveness, and detection of clinically meaningful change over time.

The system runs on a **research-grade data spine**: every datum is append-only with full
provenance and dual timestamps, corrections are written as new records rather than
overwrites, and logs and audit records carry counts and references but no health values. The
dataset is validation- and regulator-ready by construction.

## 4. What we have built today

The NSI is not a concept deck — it is a **working v1**, exercised end-to-end against synthetic
data with a comprehensive automated test suite and green continuous integration. What exists:

- **A patient application and backend.** A web app and an Android build (via Capacitor) over
  an async backend — one codebase, deployed as a public demo on synthetic data.
- **The Neuropathy Status Index engine.** The deterministic 0–100 composite (Symptoms 45 /
  Function 40 / Physiologic 15), a 30-day trend with a fixed, magnitude-independent threshold,
  a **Confidence** indicator (from data coverage and recency; adherence never enters the
  score), and an explicit "not enough data" state. It is recomputed on read — never a stored,
  mutable rollup.
- **A daily check-in.** A short function check-in, with validated-aligned **pain and numbness**
  items behind an enforced feature toggle.
- **Four ingestion paths into one record:**
  - Symptoms and daily function (patient-reported).
  - Labs from the patient's EMR via **SMART-on-FHIR** (patient-consented).
  - **BioMech** balance/gait reports (V1 ingestion; being upgraded to a direct API path —
    §8).
  - **Phone and watch mobility** via Apple Health / Health Connect — the ingestion contract
    and the in-app seam are built; the native connectors are the next step.
- **A clinician surface.** A consent-gated panel and shared patient view — a patient-held
  share the clinician cannot override.
- **A research-grade data spine.** Append-only observations with full provenance and dual
  timestamps; corrections as new records; **PHI-free** logs and audit (counts and references,
  never values).
- **Honesty guardrails, coded in.** Non-diagnostic notes co-located with every
  clinical-adjacent surface; server-enforced feature toggles; and every not-yet-licensed or
  not-yet-validated instrument stored as `validated_instrument = false`, so nothing in the
  system claims to be a validated measure that is not.

In short: the pipeline from four data streams to one explainable, confidence-qualified score
exists and runs. What it has not yet done is meet real patients — which is the point of a
test.

## 5. Why BioMech and Advanced Health, together

The two products are complementary by design:

- **BioMech's kit handles the clinical tier:** the structured, device-grade daily gait and
  balance assessment (RKM), built on the 12-channel, 100 Hz sensor precision that is BioMech's
  core IP.
- **Our app handles the real-world tier and the synthesis:** passive phone and watch mobility,
  the composite index, the patient-owned longitudinal record, and the patient-facing
  experience that BioMech's clinician-facing platform does not provide.

This is additive to BioMech's ecosystem rather than competitive with it: it combines two data
streams into a single measurement picture — clinical precision and everyday function — that
neither tier tells on its own.

## 6. The evidence base

- **Feasibility** <sub>(verified)</sub>. The literature is sufficient to develop a de-novo DPN
  composite. Outcome domains are established, and validated instruments serve as content
  anchors: NTSS-6 for sensory symptoms, and painDETECT as a neuropathic-pain screener
  (developed and validated in chronic low back pain, since applied to DPN populations). A
  recognized development pathway is codified in the **FDA Patient-Focused Drug Development
  guidance series** (Guidance 3, "Selecting, Developing, or Modifying Fit-for-Purpose Clinical
  Outcome Assessments," finalized October 23, 2025; Federal Register November 18, 2025) and
  the **COSMIN** standards. FDA Guidance 3 defines four clinical-outcome-assessment types:
  patient-reported (PRO), observer-reported (ObsRO), clinician-reported (ClinRO), and
  performance outcome (PerfO). The NSI spans three: a PRO symptom stream, a PerfO function
  stream (gait and balance), and physiologic labs.
- **The near-term method is established** <sub>(verified)</sub>. COSMIN endorses data-driven
  construction via IRT/Rasch, and IRT-based Computerized Adaptive Testing reduces respondent
  burden by roughly 41–44% without meaningfully degrading precision — the highest-evidence,
  lowest-risk improvement available to the protocol today.
- **Phone-as-base is viable but uneven** <sub>(verified)</sub>. An iPhone alone computes
  walking speed and step length with strong validity (ICC ~0.85–0.93 and ~0.76–0.85
  respectively against gold-standard gait labs). Its gait-quality metrics (asymmetry,
  double-support) are weak phone-alone and are treated as advisory. Android Health Connect
  exposes activity volume but no gait-quality types. **None of these figures has been
  validated in a neuropathy population**, which is a validation task we name explicitly.
- **Position against the current field.** The NSI is strong on coverage, objectivity,
  measurement frequency, and multimodal fusion, and **not yet established on measurement
  rigor**, since it is an unvalidated v1. In COSMIN terms, rigor means the nine measurement
  properties (content, structural, construct, and criterion validity; internal consistency,
  reliability, and measurement error; cross-cultural validity; and responsiveness), none of
  which the NSI has yet established. Feasibility, which the NSI does have, is not itself a
  measurement property under COSMIN and does not count toward rigor. Stated plainly: strong on
  design, pending on validation.

### Instrument provenance

The instruments and standards the NSI draws on, with original source, the population each was
validated in, its COA type, and licensing status. Content anchors are used as **design
references**; they are not re-validated here.

| Instrument | Original source | Validated in | COA type | Licensing |
|---|---|---|---|---|
| NTSS-6 | Bastyr, Price, Bril. Clin Ther. 2005;27(8):1278–1294. | DPN (sensory symptoms) | ClinRO (self-admin NTSS-6-SA validated separately) | Rights-holder terms to confirm |
| Norfolk QOL-DN | Vinik et al. Diabetes Technol Ther. 2005;7(3):497–508. | Diabetic neuropathy (small-fiber, large-fiber, autonomic) | PRO | Rights-holder terms to confirm |
| painDETECT | Freynhagen, Baron, Gockel, Tölle. Curr Med Res Opin. 2006;22(10):1911–1920. | Chronic low back pain (neuropathic-pain screen); later applied to DPN | PRO (screener) | Free for academic/clinical; commercial use may need permission |
| mTCNS | Bril et al. Diabet Med. 2009;26(1):240–246. | Diabetic sensorimotor polyneuropathy (early DSP) | ClinRO (clinician exam) | Rights-holder terms to confirm |
| UENS | Singleton et al. J Peripher Nerv Syst. 2008;13(3):218–227. | Early diabetic / IGT-associated neuropathy | ClinRO (clinician exam) | Rights-holder terms to confirm |
| COSMIN | Mokkink, Terwee et al. J Clin Epidemiol. 2010;63:737–745; Qual Life Res. 2010;19:539–549; Prinsen et al. 2018. | Methodology standard (PROM measurement properties) | Standard | Open methodology |
| FDA PFDD Guidance 3 | FDA. Fit-for-Purpose Clinical Outcome Assessments. Final, Oct 23, 2025; Fed. Reg. Nov 18, 2025. Docket FDA-2022-D-1385. | Regulatory guidance (COA selection/development) | Guidance | Public domain |

## 7. Where the methods are established versus still speculative

- **Established today** <sub>(evidence-backed)</sub>: adaptive testing and IRT to shorten the
  daily check-in while preserving precision; empirical weighting of the composite once real
  data accrues; passive sensing that reduces respondent burden to near zero.
- **Promising but unverified** <sub>(flagged)</sub>: machine-learning fusion of symptoms,
  wearable gait and balance, and labs to improve accuracy and predict falls and progression.
  Our verification did not substantiate the specific gains, so we treat fusion as a data asset
  to be **built and validated prospectively** rather than a claim to make today. We prefer to
  under-claim and validate rather than over-claim and be wrong.

## 8. What a test would establish — and how it makes the protocol better

The one thing a synthetic-data build cannot do is meet real patients. A test in a real DPN
population is not just a pass/fail check — it is the mechanism by which the protocol
**improves**. Specifically, a prospective test would let us:

- **Validate the index** — establish reliability, responsiveness, and the smallest change that
  is clinically meaningful (per COSMIN and FDA), converting an unvalidated v1 into a defensible
  clinical measure.
- **Replace hand-set weights with empirically-derived ones** — the current 45/40/15 weighting
  is a transparent, physician-informed starting point; real longitudinal data lets IRT/Rasch
  and factor methods derive the weighting that best tracks true change.
- **Calibrate the adaptive (IRT/CAT) layer** — tune the daily check-in to the shortest form
  that preserves precision in this population, cutting patient burden.
- **Establish phone-gait accuracy in the target population** — the published accuracy figures
  are from healthy adults; a test measures how the phone metrics behave in impaired,
  neuropathic gait, and confirms which are reliable enough to weight versus keep advisory.
- **Settle the fusion question** — determine, on real data, whether multimodal ML fusion
  delivers the accuracy and prediction gains we have deliberately flagged as unverified.

**The phased plan this implies:** deterministic v1 (now, built) → proprietary multimodal data
collection with an added IRT/CAT layer → ML-optimized, adaptive v2 with empirically-derived
weights → prospective validation → SaMD/regulatory determination (with a predetermined
change-control plan if AI is in the loop).

## 9. Honest status and the biggest risks

- **Non-diagnostic, unvalidated v1.** The largest risk is over-claiming ahead of validation.
  We manage it by labeling every clinical-adjacent surface and keeping the index a v1 measure
  pending validation.
- **Phone-gait accuracy in the target population is unproven.** This requires a validation
  study and cannot be assumed.
- **Validation is a multi-year, funded effort.** The work is genuinely hard and must be
  staffed and financed; SBIR-first is our working assumption.
- **Instrument licensing must be resolved with rights-holders** before any named validated
  instrument ships commercially, and terms differ by instrument. PROMIS is not royalty-free
  for commercial use. painDETECT is free for academic and clinical use but may require
  permission for commercial applications. NTSS-6 and Norfolk QOL-DN each carry their own
  rights-holder terms to confirm. These should be cleared instrument by instrument rather than
  assumed uniform.

## 10. Why it should be tested

The protocol is built, honest about its limits, and grounded in the current evidence. The
single thing standing between "a strong design" and "a validated measurement product" is
contact with real patients — and that is exactly what we are asking for.

To run a first test, two things are needed:

1. **BioMech clinical data flowing in.** A BioMech API or SDK so the clinical tier (per-test
   metrics, order lifecycle, and ideally raw sensor access) enters the composite as
   structured, device-grade data — replacing document parsing.
2. **A scoped prospective design** in a real DPN population, structured so the data it produces
   supports the validation in §8 (an anchor measure, consent, and the appropriate research
   governance).

**Next step:** a working session to confirm the data hand-off and scope a first prospective
test.

---

### Appendix: evidence and disclaimers

**Verification method.** Claims derive from multi-source research passes with independent
cross-checking; unverified items are flagged in-text.

**Key verified sources.** FDA PFDD Guidance 3, Fit-for-Purpose Clinical Outcome Assessments
(final Oct 23, 2025; Fed. Reg. Nov 18, 2025); COSMIN standards (Mokkink/Terwee 2010; Prinsen
2018); 2025 Diabetic Medicine systematic review of 184 DSPN trials; Griffiths 2015 (no
gold-standard DPN symptom measure); NTSS-6 (Bastyr, Price, Bril 2005); Norfolk QOL-DN (Vinik
2005); painDETECT (Freynhagen 2006); mTCNS (Bril 2009); UENS (Singleton 2008); Apple iPhone
mobility-metric validation (Nature Sci Rep 2023; Apple Heart and Movement Study, npj Digital
Medicine 2024); Android Health Connect documentation.

**Disclaimer.** Non-diagnostic; synthetic data only; not FDA-cleared; not clinical or
regulatory advice. IP is owned by Advanced Health and Wellness Group; BioMech Health is the
licensee. This document explains a protocol under development and is offered as the basis for
a testing collaboration.
