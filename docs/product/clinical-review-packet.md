# Clinical Review Packet — Scientific Soundness & Content Validity of the Neuropathy Status Index

**Date:** 2026-07-18
**Status:** Review packet — **awaiting clinical/scientific sign-off** (this document *is* the
review vehicle)
**Primary reviewer:** **Frank Fornari, PhD** (BioMech Health) — as the clinical/scientific
subject-matter reviewer
**Companion (separate reviewer, separate question):**
[`fda-regulatory-consultant-brief.md`](fda-regulatory-consultant-brief.md) — the FDA
device-status determination (decision **D2**), which is **NOT** what this packet asks for.

---

> ## ⚠️ READ THIS FIRST — WHAT THIS REVIEW IS, AND WHAT IT IS NOT
>
> This packet asks for a **scientific and clinical-content opinion**: is the Neuropathy
> Status Index (NSI) and its symptom capture **built on sound clinical measurement
> principles**, and are its items **content-valid** for diabetic/peripheral neuropathy?
> That is a **"yes / yes-with-conditions / no"** on *scientific soundness and content
> validity* — the appropriate first-pass expert gate before a formal validation study.
>
> **This review is NOT, and cannot be, any of the following:**
> - **It is NOT an FDA readiness or "ready for FDA approval" determination.** Whether the
>   software is a §201(h) device / SaMD is a regulatory-legal question routed to a qualified
>   **FDA regulatory professional** in the companion brief (decision D2). A clinical/
>   scientific reviewer — however eminent — does not make that call, and a "yes" here does
>   **not** mean the product is FDA-clearable, cleared, or exempt.
> - **It is NOT clinical validation.** Content validity (do the items measure the right
>   constructs?) is one of several psychometric properties. Reliability, construct/criterion
>   validity, responsiveness, and an MCID still require a **prospective study** (see §5).
>   This review scopes and de-risks that study; it does not substitute for it.
> - **It is NOT a diagnosis, and the product makes none.** The NSI is a **non-diagnostic
>   v1 index, pending clinical validation** (ADR-0034, ADR-0016).
>
> **Independence note (disclose, don't hide):** Dr. Fornari is CEO of **BioMech Health**, a
> **licensee and device/data partner** (ADR-0001). That makes this a well-qualified
> *scientific-soundness/content* review, but it is **not an independent validation.** A
> formal validation study (§5) should be designed and, ideally, analyzed with an
> **independent** biostatistician/psychometrician and clinician, and the BioMech
> relationship disclosed in any resulting publication or regulatory file. The Function
> domain draws on BioMech-derived metrics, which is exactly why the independence of the
> *validation* (not this content review) matters.

---

## 1. The exact decision requested

| # | Decision requested | Reviewer | What a "yes" means |
|---|---|---|---|
| **C1** | **Is the NSI construct scientifically sound and content-valid** for tracking diabetic/peripheral-neuropathy *status trend* in a patient-facing, non-diagnostic product — i.e., are the **three domains**, their **symptom-forward weighting**, the **instrument anchoring**, and the **ADA construct mapping** defensible as measurement, with the honesty caveats intact? | Dr. Fornari (clinical/scientific) | The construct is a sound basis to take into a **formal validation study** (§5); it does **not** unlock any clinical claim, marketing claim, or FDA posture. |
| **C2** | **Are the individual symptom items content-valid** for the neuropathy constructs they claim (neuropathic pain descriptors; numbness/paresthesia), and is the **ADA-construct mapping** ("related to," not "equivalent to") worded so a self-report is never overstated as an exam finding? | Dr. Fornari (clinical/scientific) | The item bank is content-valid groundwork; calibration/IRT still gated (§4, ADR-0043). |
| **C3** | **Is the deterministic trajectory logic** (per-signal direction + confidence, cross-unit honesty, staleness anchoring) a **clinically reasonable** way to present *trend* without implying diagnosis or prediction? | Dr. Fornari (clinical/scientific) | The interpretation surface is clinically reasonable as non-diagnostic trend; the SaMD/CDS line is still the consultant's call (companion brief). |

**Reviewer output requested:** for each of C1–C3, mark **yes / yes-with-conditions (list
them) / no (state why)**, plus any **content items you would add, remove, or reword**, and
the **single biggest scientific risk** you see. Conditions become groundwork items before a
validation study is designed.

## 2. Product facts a clinical reviewer needs (with repo pointers)

Everything below is **built and testable in the codebase** unless marked otherwise, and runs
on **synthetic data only** — no real patient data exists in the system.

### 2.1 What the NSI is (ADR-0034)

- A single **0–100** figure, **higher = better**, anchored to a real **"as of" date**,
  labeled **non-diagnostic v1, pending clinical validation.**
- **Three domains with LOCKED, symptom-forward weights: Symptoms 45% · Function 40% ·
  Physiologic 15%.**
  - **Symptoms (45%)** — pain + numbness/paresthesia, captured in the daily check-in,
    **anchored on NTSS-6** as the content model (exact items/scoring marked *"confirm
    against source"* — no psychometrics are invented). PROMIS is referenced as a *candidate*
    pain read and is flagged **not royalty-free for commercial use** (licensing caveat).
  - **Function (40%)** — mobility/balance. Note the **2026-07-16 amendment**: the concrete
    BioMech sub-measures originally named (sway, gait speed…) were **illustrative** and
    predate the real report format; the real catalog (Average Speed/Movement/Position,
    Impact/Single-Support Symmetry, Support Ratio, Pelvic Tilt…) is in
    [`biomech-data-streams.md`](biomech-data-streams.md). **The normalization/polarity
    mechanism stands; the specific Function sub-measures must be realigned to the real
    catalog** — a content question for this review.
  - **Physiologic (15%)** — labs (e.g. HbA1c) via LOINC/UCUM, patient-imported or EMR-pulled.
- **Anti-contradiction design (a review finding that was fixed):** card color **and** the
  arrow/delta are driven by the **one** quantity the card is about (the composite's own
  30-day delta); direction is conveyed **in words + glyph, not color alone** (WCAG 1.4.1);
  a stale value can never render as confidently fresh (`as_of` anchoring). (ADR-0034 §6.)

### 2.2 How symptoms are captured and coded (ADR-0043)

- Symptom items live in a single **`psychometrics` item bank** (`app/psychometrics/`), each
  `SymptomItem` carrying `construct`, `ada_fiber_class`, `ada_modality_related`,
  `measure_alignment`, `polarity`, and scale.
- **ADA construct mapping (honesty-guarded):** items map to the **ADA Standards of Care**
  DPN screening frame (temperature/pinprick → small fiber; 128-Hz vibration → large fiber;
  annual 10-g monofilament; Rec 12.17–12.18). The mapping is explicitly **`ada_modality_related`
  = "related to," never "equivalent to"** — a patient-reported symptom mapped to the fiber
  *construct* the ADA exam assesses, **never presented as a monofilament/tuning-fork result.**
- **Uncalibrated by design:** `is_calibrated = False`; the administration stub is
  `FixedOrderSelector` (`is_adaptive = False`) + `SumScoreEstimator` (`is_irt = False`).
  No item claims a validated instrument; tests enforce these honesty guards. The ADA keys
  are **additive provenance only** — the NSI score does not read them, so the score is
  provably unchanged by the mapping.

### 2.3 How trend is computed and presented (ADR-0003/0016)

- A **deterministic, explainable** engine fits a per-signal line and reports **direction +
  confidence + per-signal sourced drivers + data gaps** — no black box.
- **Non-diagnostic note co-located** with every surfaced direction (`NonDiagnosticNote`,
  ADR-0016); cross-unit deltas are refused ("unit changed / not judged") rather than
  computing a misleading better/worse across unit changes (ADR-0015).
- **AI narration** is a warmth-rephrasing of the deterministic result — **off by default,
  BAA-gated, never in the request path, and it never diagnoses, doses, or asserts
  causation** (ADR-0011/0020/0040).

### 2.4 What is explicitly NOT claimed (load-bearing for the review)

- **No instrument psychometrics are invented.** Uncertain specifics are marked *"confirm
  against source."*
- The product **ingests, graphs, analyzes** — it does **not** measure, diagnose, or
  recommend treatment (ADR-0003).
- The algorithm is flagged **unvalidated** in the FDA gap register; the index is deliberately
  kept **non-diagnostic v1**.

## 3. The clinical/content questions to review

Each row is a **question for the reviewer**, not a claim by us.

| # | Question for Dr. Fornari | Anchor |
|---|---|---|
| **Q1** | Are **three domains (Symptoms / Function / Physiologic)** the right decomposition of neuropathy *status* for trend tracking, and is the **symptom-forward 45/40/15** weighting clinically defensible for a patient-facing index (vs. e.g. equal weight, or a data-driven weight — see §4)? | ADR-0034 §1 |
| **Q2** | Is **NTSS-6** the right content anchor for the Symptom domain (neuropathic pain descriptors + numbness/paresthesia in one short DPN instrument), and are there **specific items you would add/remove/reword**? Any content gaps (e.g. allodynia, nocturnal burden, autonomic symptoms)? | ADR-0034 §1 |
| **Q3** | Is the **ADA construct mapping** (self-report items → small/large-fiber constructs, "related to" not "equivalent to") **honest and useful**, or does any wording risk implying an exam-grade result? | ADR-0043 |
| **Q4** | For **Function**, which **real BioMech catalog** metrics ([`biomech-data-streams.md`](biomech-data-streams.md)) are the **clinically meaningful** balance/gait indicators for neuropathy status, and what is each metric's **polarity** (higher = better or worse)? This directly realigns the illustrative sub-measures per the 2026-07-16 amendment. | ADR-0034 amendment |
| **Q5** | Is **HbA1c (+ any other labs you'd include)** the right, and correctly-weighted (15%), Physiologic contributor for a *status trend* — recognizing HbA1c is a glycemic-control proxy, not a neuropathy measure? | ADR-0034 §1 |
| **Q6** | Is presenting a **0–100 composite with a 30-day delta and confidence**, non-diagnostically, a **clinically reasonable trend surface** — or does a single number risk over-simplifying in a way that could mislead a 60+ patient (false reassurance / false alarm)? | ADR-0034; ADR-0039 |
| **Q7** | What is the **minimum evidence** you would want before the index could carry any language stronger than "trend visualization" — i.e., what does the validation study in §5 need to show? | §5 |

## 4. Open measurement decisions (gated — your input shapes them)

These are **deliberately deferred** and honest; the reviewer's answers steer them (ADR-0043
"open decisions"):

1. **A-priori vs. data-driven weights.** The 45/40/15 weights are a clinical prior. Should
   final weights be derived (IRT/Rasch, factor analysis) from prospective data? (Evidence
   review: [`ai-fusion-evidence-review.md`](ai-fusion-evidence-review.md).)
2. **IRT/CAT.** The item bank has an uncalibrated IRT/CAT seam. Calibration needs a
   prospective sample; CAT is the documented respondent-burden lever but claims precision we
   don't yet have. When (and with what N) is calibration worth it?
3. **Instrument licensing.** NTSS-6 / PROMIS / Norfolk QOL-DN / MNSI licensing differs;
   PROMIS is **not** royalty-free commercially ([`instrument-licensing-research.md`](instrument-licensing-research.md)).
   Which instruments are content anchors vs. licensed components?

## 5. What a formal validation study would need (scope-check, not a claim)

Offered so the reviewer can judge **feasibility and design**, per the FDA PRO guidance /
COSMIN framing summarized in
[`ai-augmented-protocol-feasibility.md`](ai-augmented-protocol-feasibility.md):

- **Content validity** — concept elicitation + cognitive interviews with DPN patients
  (this review is the expert-panel front end of that).
- **Reliability** — internal consistency + test–retest.
- **Construct/criterion validity** — against established measures (MNSI, Norfolk QOL-DN,
  Total Neuropathy Score) and, where feasible, exam findings.
- **Responsiveness + MCID** — does the index move with real change, and by how much is
  meaningful?
- **Sample/design** — sized per the psychometric targets; independent biostatistician.

**Reviewer question (Q7 restated):** is this the right study, and what would you change?

## 6. Disclosed limitations (not hidden)

1. **Unvalidated algorithm; non-diagnostic v1** (FDA gap register).
2. **Synthetic data only; no prospective data yet** — nothing here is a psychometric result.
3. **Function sub-measures pending realignment** to the real BioMech catalog (§2.1, Q4).
4. **Instrument specifics marked "confirm against source"** — not yet source-verified.
5. **Independence:** this is a partner (BioMech) scientific review, not independent
   validation (see the top caveat).
6. **The FDA/SaMD question is separate and open** — companion brief, decision D2.

## 7. Sign-off sheet

| Field | Clinical/scientific reviewer |
|---|---|
| Name / credential | ______________________ (Frank Fornari, PhD — BioMech Health) |
| Relationship / COI disclosed | ______________________ (BioMech = licensee/device partner, ADR-0001) |
| **C1** NSI construct sound & content-valid | ☐ Yes ☐ Yes w/ conditions ☐ No |
| **C2** Symptom items content-valid + ADA mapping honest | ☐ Yes ☐ Yes w/ conditions ☐ No |
| **C3** Trajectory surface clinically reasonable (non-diagnostic) | ☐ Yes ☐ Yes w/ conditions ☐ No |
| Content changes (add/remove/reword — attach) | ______________________ |
| Biggest scientific risk | ______________________ |
| Conditions (become pre-validation groundwork items) | ______________________ |
| Signature / date | ______________________ |

---

> ## ⚠️ CAVEAT (bottom — same weight as the top)
>
> **A scientific/content-validity opinion only — NOT an FDA determination, NOT clinical
> validation, NOT a diagnosis.** A "yes" here means the construct is sound enough to take
> into a formal validation study; it authorizes no clinical claim, no marketing claim, and
> no regulatory posture. The FDA device-status question is answered by a qualified FDA
> regulatory professional in the companion brief (decision D2). The product is **not
> FDA-cleared, -listed, or -registered**, is **not clinically validated**, and processes
> **synthetic data only.**
