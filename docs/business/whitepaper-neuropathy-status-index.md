# The Neuropathy Status Index
### An AI-augmented, multimodal protocol for measuring diabetic peripheral neuropathy — continuously, objectively, and in daily life

**Prepared for:** Frank Fornari, PhD — CEO & Founder, BioMech Health
**Prepared by:** Advanced Health and Wellness Group (IP owner; BioMech Health, licensee)
**Date:** July 2026 · **Status:** Proposal for partnership discussion — *Confidential*

> **On honesty (up front).** This paper describes a **non-diagnostic v1** protocol validated
> against **synthetic data only**. It is **not** FDA-cleared, **not** clinically validated,
> and makes **no** diagnosis. Every empirical claim below was produced by a multi-source,
> **adversarially-verified** research process; where the evidence is strong we say so, and
> where a claim is promising-but-unverified we flag it explicitly. This is not clinical or
> regulatory advice — final scientific and regulatory sign-off rests with qualified experts.

---

## 1. Executive summary

Diabetic peripheral neuropathy (DPN) is one of the most consequential and least well-measured
complications of diabetes. Today it is assessed with **siloed, episodic, single-modality**
instruments — a questionnaire *or* a clinic exam *or* a QoL survey, each at a point in time.
Our verified review of the literature found **no longitudinal, multimodal composite** that
fuses patient-reported symptoms, objective gait/balance, and labs into a single score that
moves with the patient over time. **That gap is the opportunity.**

We propose the **Neuropathy Status Index (NSI)** — a composite 0–100 measure built from four
signal streams, updated **daily**, presented with an explicit confidence indicator, and
engineered to a research-grade data standard from the first row. It is designed to run
**alongside BioMech's clinical platform**, not compete with it:

- **BioMech provides the clinical tier** — device-grade daily gait and balance (RKM).
- **Our app provides the real-world tier** — passive phone/watch mobility — **plus** the
  composite index, the patient-facing experience, and the longitudinal record.
- Together this produces the one asset a competitor cannot copy: a **proprietary, consented,
  daily, multimodal longitudinal dataset** on neuropathy progression.

The near-term AI value is **proven measurement science** (adaptive testing / IRT to cut
respondent burden, data-driven scoring). The longer-term value — multimodal ML fusion — is
**promising but not yet validated**, and we treat it accordingly. The result is a protocol
that is **leading on design and honest about validation**: a credible scientific contribution
and a defensible commercial position, provided the validation work is funded and done.

## 2. The problem: neuropathy is under-measured

- **Human and economic stakes.** Peripheral neuropathy drives falls, mobility decline, and
  loss of independence in an aging population — the same population and the same fall-risk
  economics BioMech already targets.
- **The measurement is fragmented (verified).** A 2025 systematic review of 184 DSPN trials
  found consistent outcome *domains* (pain, nervous-system symptoms, physical function, QoL)
  but **severe instrument heterogeneity** — 32 different nervous-system tools and 35 distinct
  physical-function tools across trials. A 2015 review concluded there is still **no
  gold-standard DPN symptom measure**, and the 2022–2025 literature confirms the gap is open.
- **Every established instrument is siloed and episodic (verified).** NTSS-6 (sensory
  symptoms, patient-reported), Norfolk QOL-DN (quality of life), the mTCNS and UENS (clinician
  exams), the 10-g monofilament and vibration tests — each is validated, but each captures
  *one* construct at a *single visit*. None is continuous; none is multimodal.

A patient's neuropathy is a **trajectory**. Measuring it with disconnected snapshots is the
core problem the NSI is designed to solve.

## 3. The proposal: the Neuropathy Status Index

A deterministic, explainable, non-diagnostic composite that fuses four streams into one
0–100 score (higher = better), recomputed continuously and shown with a confidence level:

| Domain | Signal | Source & cadence | Basis |
|---|---|---|---|
| **Symptoms** | Pain + numbness/paresthesia | Patient self-report, **daily** | NRS / NTSS-6-aligned |
| **Function — clinical** | Gait + balance | **BioMech, daily** (device-grade) | IMU gait, mCTSIB-style balance |
| **Function — real-world** | Everyday mobility | **Phone (base) + watch (optional)** | Apple Health / Health Connect |
| **Physiologic** | HbA1c and related labs | EMR via SMART-on-FHIR | LOINC |

**Three properties make it distinctive:**

1. **Multimodal fusion into one score** — the documented gap, filled.
2. **Two-tier function** — proving a patient improves both in the *clinic test* (BioMech) and
   in *daily life* (phone/watch), with the consumer-grade signal weighted for fidelity so it
   never masquerades as device-grade. This "better in the clinic **and** better in daily
   living" story is the value-based-care and payer argument.
3. **A daily curve, not a snapshot** — which is what actually powers trend detection,
   responsiveness, and clinically meaningful change over time.

All of it sits on a **research-grade data spine**: every datum is append-only with full
provenance and dual timestamps; corrections are new records, never overwrites; logs and
audit carry counts and references, **never health values**. The dataset is
validation- and regulator-ready *by construction*.

## 4. Why BioMech + Advanced Health, together

The two products are **complementary by design**:

- **BioMech's kit does the clinical tier** — the structured, device-grade daily gait/balance
  assessment (RKM), with the 12-channel, 100 Hz sensor precision that is BioMech's core IP.
- **Our app does the real-world tier and the synthesis** — passive phone/watch mobility, the
  composite index, the patient-owned longitudinal record, and the patient-facing experience
  that BioMech's clinician-facing platform does not provide.

This is additive to BioMech's ecosystem, not competitive with it — and it turns two data
streams into a compounding asset. **The durable moat is the dataset**: a daily, consented,
multimodal longitudinal record of neuropathy progression is something no competitor can buy or
reverse-engineer. A validated composite index and adaptive measurement layer sit on top of it.

## 5. The evidence base (grounded and adversarially verified)

- **Feasibility (verified).** The published literature *is* sufficient to develop a de-novo
  DPN composite: the domains are established, validated instruments (NTSS-6, painDETECT) serve
  as content anchors, and a recognized development pathway is codified in the **FDA
  Patient-Focused Drug Development guidance series** (Guidance 3 finalized Oct/Nov 2025) and
  the **COSMIN** measurement standards.
- **The near-term AI lever is proven (verified).** COSMIN endorses **data-driven construction
  via IRT/Rasch** (not just hand-set weights), and IRT-based **Computerized Adaptive Testing**
  reduces respondent burden **~41–44%** without meaningfully degrading precision — the highest-
  evidence, lowest-risk way AI improves the protocol today.
- **Phone-as-base is real but uneven (verified — and stated honestly).** An iPhone *alone*
  computes walking speed and step length with **strong validity** (ICC ~0.85–0.93 / ~0.76–0.85
  vs. gold-standard gait labs); its gait-*quality* metrics (asymmetry, double-support) are
  **weak phone-alone** and are treated as advisory. Android Health Connect exposes activity
  volume but **no gait-quality types**. Crucially, **none of these figures has been validated
  in a neuropathy population** — a validation task we name explicitly, not paper over.
- **The landscape grade.** Against the current field, the NSI grades **strong on coverage,
  objectivity, measurement frequency, and multimodal fusion**, and **not-yet-established on
  measurement rigor** (it is an unvalidated v1). The honest verdict: *leading on design,
  pending on validation.* The established instruments are the mirror image — narrow and
  episodic, but validated.

## 6. Where AI adds real value — vs. where it is still speculative

- **Real today (evidence-backed):** adaptive testing / IRT to shorten the daily check-in
  while preserving precision; data-driven (empirical) weighting of the composite once real
  data accrues; and passive sensing that lowers burden to near zero.
- **Promising but unverified (flagged):** machine-learning *fusion* of symptoms + wearable
  gait/balance + labs to improve accuracy and predict falls/progression. Our verification pass
  did **not** substantiate the specific accuracy or outcome gains, so we treat multimodal
  fusion as **moat substrate to be earned through data and validated prospectively** — not as
  a claim to make today. This discipline is deliberate: we would rather under-claim and
  validate than over-claim and be wrong.

## 7. A realistic phased plan

1. **Deterministic v1 (now).** The composite with transparent, hand-set weights, honest
   "pending validation." Already built and running against synthetic data.
2. **Proprietary multimodal data collection.** Accumulate the daily four-stream longitudinal
   record — the moat substrate — while adding an IRT/CAT layer to the symptom check-in.
3. **ML-optimized / adaptive v2.** Move from hand-set to empirically-derived weights; add
   sensor-derived signals *only as they validate*.
4. **Prospective validation.** Reliability, construct/criterion validity, responsiveness, and
   clinically meaningful change per COSMIN + FDA guidance — the step that converts
   `validated_instrument: false` into a defensible clinical claim.
5. **Regulatory.** SaMD determination and, if AI-in-the-loop, a predetermined change-control
   plan.

## 8. Honest status and the biggest risks

- **Non-diagnostic, unvalidated v1.** The single largest risk is over-claiming ahead of
  validation. We manage it by labeling every clinical-adjacent surface and keeping the index a
  v1 measure pending validation.
- **Phone-gait accuracy in the target population is unproven** — a required validation study,
  not an assumption.
- **Validation is a multi-year, funded effort** — the moat is real *because* it is hard; it
  must be staffed and financed (an SBIR-first path is our working assumption).
- **Instrument licensing** (e.g., NTSS-6, PROMIS) must be resolved with rights-holders before
  any named validated instrument ships commercially — PROMIS in particular is **not**
  royalty-free for commercial use.

## 9. What we propose — the ask

To move from a strong design to a validated product, we propose a focused collaboration:

1. **Data hand-off / API access.** Confirm a BioMech **API/SDK** so the clinical tier
   (per-test metrics, order lifecycle, and ideally raw sensor access) flows into the composite
   as structured, device-grade data — replacing brittle document parsing.
2. **Joint validation.** Co-design the prospective validation study (BioMech's clinical
   footprint + our composite and dataset) to establish the NSI's psychometrics in a real DPN
   population.
3. **Aligned positioning.** A shared, honest narrative: BioMech's clinical precision + our
   real-world, patient-owned, longitudinal index — one measurement story for clinicians,
   payers, and patients.

**Next step:** a working session to confirm the data hand-off and scope the validation plan.

---

### Appendix — evidence & disclaimers

- **Verification method.** Claims above derive from multi-source research passes with
  three-vote adversarial verification; unverified items are flagged in-text.
- **Key verified sources.** FDA PFDD guidance series (Guidance 3, 2025); COSMIN measurement
  standards (Terwee 2018; Mokkink 2010/2018); 2025 *Diabetic Medicine* systematic review of
  184 DSPN trials; Griffiths 2015 (no gold-standard DPN symptom measure); NTSS-6 (Bastyr
  2005); Apple iPhone mobility-metric validation (Nature Sci Rep 2023; Apple Heart & Movement
  Study, npj Digital Medicine 2024); Android Health Connect documentation. Full transcripts on
  file.
- **Companion documents.** `docs/product/ai-augmented-protocol-feasibility.md`,
  `docs/product/protocol-grade-vs-landscape.md`, `docs/product/biomech-data-streams.md`,
  `docs/decisions/…-adr-0034-neuropathy-status-index.md`,
  `docs/decisions/…-adr-0035-phone-base-adl-health-bridge.md`.
- **Disclaimer.** Non-diagnostic; synthetic data only; not FDA-cleared; not clinical or
  regulatory advice. IP is owned by Advanced Health and Wellness Group; BioMech Health is the
  licensee. This document is a partnership proposal, not an offer of securities.
