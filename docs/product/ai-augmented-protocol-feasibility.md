# AI-augmented neuropathy protocol — feasibility, evidence, and the moat

**Question:** Is there enough published literature to develop and validate our *own* neuropathy
status-measurement protocol (a patient-reported + multimodal composite for diabetic/peripheral
neuropathy covering pain, numbness/paresthesia, balance/gait, and function), and where can AI/ML
defensibly improve its accuracy and outcomes as a durable moat?

> **Not clinical, scientific, or regulatory advice.** This is background research to inform a
> product decision. Final scientific and regulatory sign-off rests with qualified experts
> (a psychometrician/biostatistician, a neurology PI, and regulatory counsel). Every claim below
> is tagged by how strongly this research pass could stand behind it:
> **✅ Verified** (survived 3-vote adversarial verification, high confidence),
> **🔎 Surfaced-only** (a real source was found but the claim was **not** verified in this pass —
> treat as a lead, not a finding), and **⚠️ Judgment** (our reasoning, labeled as such).
> Companion: [`instrument-licensing-research.md`](instrument-licensing-research.md) (who owns the
> instruments we'd anchor to and what a commercial license costs).

## TL;DR

- **Feasibility (Part A) is well-supported.** ✅ The published literature is sufficient to build a
  *de-novo* DPN composite: the outcome **domains** are established and consistent (pain,
  nervous-system/neuropathy symptoms, physical functioning, quality of life), while existing
  **instruments** are so heterogeneous that a 2025 systematic review of 184 trials found **32
  different nervous-system tools and 35 physical-functioning tools** and explicitly called for a
  standardized core outcome set. There is **no gold-standard DPN symptom PRO** — a documented,
  still-open gap a well-validated composite could fill.
- **The development pathway is codified.** ✅ FDA's four-part **Patient-Focused Drug Development
  (PFDD)** guidance series (Guidance 3 finalized **Oct/Nov 2025**) and the **COSMIN** standards
  prescribe a concrete qualitative-then-quantitative route: concept elicitation → cognitive
  interviews → psychometric evaluation across nine measurement properties, with **content
  validity established first**.
- **The strongest *near-term* AI lever is measurement science, not sensor ML.** ✅ COSMIN
  endorses **data-driven construction via IRT/Rasch** (not just a-priori weighting), and IRT-based
  **Computerized Adaptive Testing (CAT)** demonstrably cuts respondent burden **~41–44%** without
  meaningfully degrading precision. This is the AI/ML claim the evidence *most* supports today.
- **The multimodal-fusion "moat" is a lead, not a proven finding — yet.** 🔎 Searches found real
  sources on wearable gait/balance biomarkers, ML fusion, and the FDA AI/ML-SaMD framework
  (GMLP/PCCP), but **none of those claims survived verification in this pass** (they were dropped
  before the verification budget, not refuted). So we can say the moat is *plausible and
  literature-adjacent*, but we **cannot yet substantiate** specific accuracy/outcome gains. A
  dedicated second research pass is required before any commercial or regulatory commitment rests
  on the AI-fusion story.
- **⚠️ Recommendation:** proceed with a **deterministic, evidence-anchored v1 composite** now
  (feasible and defensible), instrument the product to **accumulate a proprietary longitudinal
  multimodal dataset** from day one, and treat **IRT/CAT** as the first AI upgrade — while running
  the follow-up research that either confirms or deflates the sensor-fusion moat before we build
  on it.

## Part A — Is the literature sufficient to build our own instrument? (Yes)

### A1. The domains are settled; the instruments are a mess — that gap is the opportunity ✅

A 2025 *Diabetic Medicine* systematic review of **184 interventional DSPN trials** found consistent
outcome-**domain** reporting — nervous-system/neuropathy outcomes (primary in 174 trials), pain
(primary in 127 trials, 69%), physical functioning, and quality of life — but **severe instrument
heterogeneity**: 32 different nervous-system measuring tools (20 for pain) and 35 distinct
physical-functioning tools, with an explicit call for a **core outcome set with standardized
tools**. A 2015 systematic review (Griffiths et al., *J Diabetes Complications*) states plainly:
"There remains a need for a gold standard for DPN symptom assessment. Few existing instruments are
adequately validated and the domains assessed are inconsistent." 2022–2025 literature confirms the
gap is still open.

> **What this means for us:** we are not inventing constructs from nothing — the *what to measure*
> is established. The unmet need is a **single, well-validated, standardized composite**. That is a
> credible scientific contribution, not a vanity metric.

- Sources: [PMC12535334 (2025 review, 184 trials)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12535334/),
  [Griffiths 2015 (no gold standard)](https://www.sciencedirect.com/science/article/abs/pii/S105687271500361X)

### A2. Validated content anchors exist ✅

The **NTSS-6** supplies six evidence-based sensory-symptom items — numbness/insensitivity,
prickling/tingling, burning, aching pain/tightness, sharp/shooting/lancinating pain,
allodynia/hyperalgesia — each rated by frequency and intensity, with strong psychometrics
(Cronbach's α > 0.7, test-retest ICC > 0.9, construct validity r = 0.773–0.885). It maps almost
exactly onto our pain + numbness domains. **painDETECT's** history is a cautionary precedent worth
internalizing: its original 9-item form **failed Rasch fit** and reached unidimensionality only
after rescoring four items and dropping two (revised 7-item scale, n = 624) — concrete evidence
that **a-priori item sets typically need psychometric refinement**, which is exactly what our
data-driven phase is for.

- Sources: [NTSS-6 (Bastyr 2005)](https://pubmed.ncbi.nlm.nih.gov/16199253/),
  [painDETECT Rasch refinement (PMC5336691)](https://pmc.ncbi.nlm.nih.gov/articles/PMC5336691/)
- **Licensing caveat:** anchoring to (or reproducing) NTSS-6 items is a *licensed* act — see
  [`instrument-licensing-research.md`](instrument-licensing-research.md). "Content anchor" here
  means *evidence for which constructs matter*, not permission to copy items.

### A3. The regulatory + academic development pathway is codified ✅

**FDA PFDD guidance series (four parts).** Guidance 2 codifies **concept elicitation** (qualitative
identification of symptoms/impacts meaningful to patients, via interviews and interview-guide
development to establish content validity). Guidance 3 — *"Selecting, Developing, or Modifying
Fit-for-Purpose Clinical Outcome Assessments"*, **finalized Oct 23 2025 (Federal Register notice
Nov 18 2025)** — covers all four COA types (PRO, ObsRO, ClinRO, PerfO). "Fit-for-purpose" means the
**evidentiary burden scales with the context of use** (exploratory vs. registrational endpoint),
and FDA ties scores to **meaningful within-patient change**.

**COSMIN** provides the academic framework: content validity = **relevance + comprehensiveness +
comprehensibility**, established **first**; then internal structure; then reliability, measurement
error, criterion/construct validity, and responsiveness — a taxonomy of **nine measurement
properties in three domains** (reliability, validity, responsiveness).

> **Caveats (flagged in verification):** FDA guidances are **legally nonbinding recommendations** —
> "required" overstates their force; they function as de-facto standards. FDA's precise phrase is
> "meaningful **within-patient** change," not "clinical benefit." Guidance 4 (incorporating COAs
> into endpoints) is **still in draft** — the pathway is current as of mid-2026 but still settling.

- Sources: [FDA PFDD Guidance 3](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/patient-focused-drug-development-selecting-developing-or-modifying-fit-purpose-clinical-outcome),
  [FDA PFDD series overview](https://www.fda.gov/drugs/development-approval-process-drugs/fda-patient-focused-drug-development-guidance-series-enhancing-incorporation-patients-voice-medical),
  [COSMIN content-validity (Terwee 2018, PMC5891557)](https://pmc.ncbi.nlm.nih.gov/articles/PMC5891557/),
  [COSMIN manual (2018)](https://www.cosmin.nl/wp-content/uploads/COSMIN-syst-review-for-PROMs-manual_version-1_feb-2018.pdf)

### A4. Data-driven construction beats a-priori weighting — and is endorsed ✅

The COSMIN manual explicitly legitimizes **IRT/Rasch** alongside Classical Test Theory for
evaluating measurement properties. A worked comparison (Petrillo et al. 2015, *Value in Health*,
NEI-VFQ-25, n = 240) found CTT, IRT, and Rasch reached broadly comparable overall conclusions, but
**IRT/Rasch surfaced extra diagnostics** — item misfit, local dependence, poor targeting — that
directly inform scale refinement. This is the methodological basis for moving our composite from
**hand-set weights (ADR-0034's Symptoms 45 / Function 40 / Physiologic 15)** to **empirically
derived weights** once we have data.

> **Caveat:** COSMIN endorses IRT/Rasch for *property evaluation*; extending that to "composite
> construction / data-driven scoring" is a reasonable but mild interpretive stretch, flagged here
> honestly.

- Sources: [Petrillo 2015 (CTT/IRT/Rasch worked examples)](https://www.valueinhealthjournal.com/article/S1098-3015(14)04730-5/fulltext),
  [COSMIN manual](https://www.cosmin.nl/wp-content/uploads/COSMIN-syst-review-for-PROMs-manual_version-1_feb-2018.pdf)

## Part B — Where AI/ML improves accuracy & outcomes (the honest split)

### B1. Proven today: adaptive measurement (IRT/CAT) ✅ — the strongest near-term lever

IRT-based **Computerized Adaptive Testing** measurably reduces respondent burden. In a
peer-reviewed study of Dutch-Flemish PROMIS pediatric CAT stopping rules, an optimized
standard-error-reduction rule cut administered items from **~9.98 → ~5.58 for anxiety (~44%)** and
**~8.13 → ~4.79 for depressive symptoms (~41%)**, while mean T-score differences for non-floor
participants were only **0.04–0.58 points** ("did not produce any substantial T-score differences
or diminishments in reliability for non-floor participants").

> **Scope caveat (important):** this evidence is **pediatric anxiety/depression, not DPN**. It
> substantiates CAT/IRT as a *general method* for burden reduction, not neuropathy-specific
> performance — and **floor participants did show 3–4 point differences**. A DPN item bank would
> need its own calibration and CAT-precision study.

**⚠️ Why this is the moat's real front door:** a shorter, adaptive daily check-in that preserves
precision directly improves **adherence** (fewer items → more completed check-ins → more
longitudinal data), which compounds into the dataset that everything else depends on. It is the AI
lever with both the **best evidence** and the **lowest regulatory/technical risk** — and it builds
on measurement science we can start calibrating as soon as we have response data.

- Source: [PROMIS pediatric CAT stopping rules (PMC12681468)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12681468/)

### B2. Not yet substantiated: multimodal ML fusion, sensor biomarkers, ML prediction 🔎

**This is the critical honesty point.** Of the 24 claims that survived three-vote adversarial
verification, **all** address Part A (feasibility, anchors, FDA/COSMIN pathway) and B1 (CAT/IRT).
**No verified claim** substantiates:

- ML **fusion** of patient-reported symptoms + wearable gait/balance + labs improving accuracy;
- sensor-derived **gait/balance digital biomarkers** validated for DPN and predictive of
  falls/progression;
- ML **early detection / progression / fall-risk prediction** improving *outcomes* (not just
  AUC);
- the **FDA AI/ML-SaMD framework** (GMLP, Predetermined Change Control Plan, SaMD action plan)
  requirements for an AI-in-the-loop measurement product.

The search phase **did surface real, on-topic sources** for these (below) — they were **dropped
before the verification budget**, not refuted. So the correct reading is: *promising leads, not
findings.* **Do not put "AI fusion beats single-modality by X%" in a pitch deck, a spec, or a
regulatory submission on the strength of this pass.** These are the open questions a dedicated
follow-up research run must close.

Surfaced-but-unverified leads (cite only after verification):
- [Wearable sensors — postural sway & fall risk in diabetic foot neuropathy (PubMed 37852919)](https://pubmed.ncbi.nlm.nih.gov/37852919/)
- [Development & multicenter external validation model (Karger)](https://karger.com/ger/article-abstract/doi/10.1159/000551704/947544/Development-and-Multicenter-External-Validation-of)
- [Multimodal ML / digital biomarker source (PMC11649904)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11649904/),
  [(PMC12324740)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12324740/)
- [FDA — PCCP for ML-enabled devices (guiding principles)](https://www.fda.gov/medical-devices/software-medical-device-samd/predetermined-change-control-plans-machine-learning-enabled-medical-devices-guiding-principles),
  [FDA AI-enabled device software lifecycle management (Federal Register 2025)](https://www.federalregister.gov/documents/2025/01/07/2024-31543/artificial-intelligence-enabled-device-software-functions-lifecycle-management-and-marketing)

## Part C — The moat and a phased plan (⚠️ our judgment, evidence-anchored)

The verified corpus does **not** by itself prove where durable advantage forms (Part C was
unaddressed by surviving claims). The following is **our reasoning**, anchored to what *was*
verified and labeled as judgment.

### Where the defensible moat most plausibly sits

1. **A proprietary longitudinal, multimodal, consented dataset.** The one asset a competitor
   cannot copy, buy, or reverse-engineer is *our patients' real, longitudinal, multi-stream data*
   (symptoms + BioMech gait/balance + labs) tied to outcomes. Everything else (a composite formula,
   a CAT engine) is replicable science; the **dataset** is the compounding asset. This is why we
   instrument for data capture from v1 even before the ML exists.
2. **A validated, standardized composite index** filling the documented gold-standard gap (A1).
   Validation is a moat because it is **expensive, slow, and citable** — and because payers and
   clinicians adopt what is validated.
3. **Adaptive, calibrated measurement (IRT/CAT)** tuned on our own item bank — better precision per
   respondent-minute than any static questionnaire a competitor ships.
4. **Algorithmic change control done right** (once we go ML-SaMD) — a defensible *regulatory*
   posture (a PCCP that lets the model improve within an agreed envelope) is itself a barrier. 🔎
   This depends on the FDA AI/ML-SaMD research we have **not** yet verified.

### Phased plan (each phase gates the next)

- **Phase 1 — Deterministic v1 composite (now; feasible ✅).** Ship the current NSI with
  transparent, hand-set weights and honest `validated_instrument: false`. Anchor content to
  established constructs (A1–A2). **Instrument for data capture from day one** — every check-in,
  BioMech report, and lab stored append-only with provenance (already true per ADR-0006).
- **Phase 2 — Proprietary multimodal data collection + measurement science.** Accumulate the
  longitudinal dataset. In parallel, run the **IRT/Rasch calibration** on symptom items and pilot a
  **DPN-specific CAT** (B1) — the highest-evidence, lowest-risk AI upgrade. Begin formal
  **concept-elicitation + cognitive-interview** work (A3) toward content validity.
- **Phase 3 — ML-optimized / adaptive v2.** *Gated on the follow-up research (B2) actually
  substantiating multimodal fusion.* Move from hand-set to **empirically derived weights** (A4);
  add sensor-derived digital biomarkers **only if** they validate for DPN and predict
  falls/progression. Design against the FDA AI/ML-SaMD framework (GMLP/PCCP) from the start.
- **Phase 4 — Prospective validation.** A prospective study evaluating reliability, construct/
  criterion validity, responsiveness, and MCID per COSMIN + PFDD (A3). This is what converts
  `validated_instrument: false` to a defensible clinical claim.
- **Phase 5 — Regulatory.** SaMD/device determination and (if AI-in-the-loop) a PCCP-based change
  control plan. **Open — requires the unverified B2/regulatory research and qualified counsel.**

### Biggest risks (⚠️)

- **Overclaiming the AI moat before it's proven.** The single largest risk surfaced by this pass:
  the fusion/sensor/prediction story is *unverified*. Building product, fundraising narrative, or
  regulatory strategy on it before the follow-up research is a real liability. **Sequence the
  research before the spend.**
- **Validation cost/time.** A gold-standard composite is a multi-year, multi-cohort effort; the
  moat is real *because* it is hard — but it must be funded and staffed (ties to
  [`../business/funding-strategy.md`](../business/funding-strategy.md), SBIR-first).
- **Regulatory drift.** FDA PFDD Guidance 4 is still draft; the AI/ML-SaMD framework is evolving —
  design for change control, don't hard-code to a snapshot.
- **Instrument licensing.** Anchoring to NTSS-6/PROMIS constrains what we can reproduce — resolve
  per [`instrument-licensing-research.md`](instrument-licensing-research.md).

## What this pass verified vs. what it did not (the honest ledger)

| Question | Verdict |
| --- | --- |
| A1 Literature sufficient to build a de-novo DPN composite | ✅ Verified (high) |
| A2 Validated content anchors (NTSS-6, painDETECT) exist | ✅ Verified (high) |
| A3 FDA PFDD + COSMIN development pathway codified | ✅ Verified (high) |
| A4 Data-driven (IRT/Rasch) construction endorsed | ✅ Verified (high) |
| B1 (Q4) CAT/IRT reduces burden ~41–44% w/o precision loss | ✅ Verified (high; non-DPN evidence) |
| B2 (Q5) Multimodal ML fusion accuracy gains | 🔎 Surfaced only — **not verified** |
| B2 (Q6) Sensor gait/balance biomarkers validated for DPN | 🔎 Surfaced only — **not verified** |
| B2 (Q7) ML progression/fall prediction improves outcomes | 🔎 Surfaced only — **not verified** |
| B2 (Q8) FDA AI/ML-SaMD framework (GMLP/PCCP) requirements | 🔎 Surfaced only — **not verified** |
| C (Q9–Q10) Where durable moat forms; phased recommendation | ⚠️ Judgment, evidence-anchored |

**Verification stats:** 5 search angles → 23 sources fetched → 106 claims extracted → 25 verified
(24 confirmed, 1 refuted, 0 unverified); 7 findings after synthesis. One claim was **refuted** (a
specific "12 DPN-validated PRO studies" count from the Griffiths review, 1-2 vote) and is excluded.

## Immediate next actions (owner)

1. **Run the dedicated follow-up research pass** to close B2/C: multimodal ML fusion evidence,
   validated DPN gait/balance digital biomarkers, ML fall/progression prediction *outcomes*, and
   the FDA AI/ML-SaMD (GMLP/PCCP/SaMD action plan) requirements — with the same adversarial
   verification, *before* any of it drives product or fundraising claims.
2. **Keep building Phase 1** (deterministic v1) and **preserve the append-only multimodal data
   capture** — the dataset is the moat regardless of how B2 resolves.
3. **Engage a psychometrician / biostatistician** to scope the IRT/Rasch calibration + DPN CAT
   (Phase 2) — the highest-evidence AI lever.
4. **Have regulatory counsel + a neurology PI** own the validation and SaMD determination — this
   document does not.

## Sources

Verified primary/authoritative sources: 2025 *Diabetic Medicine* DSPN outcomes review (PMC12535334);
Griffiths 2015 DPN symptom-assessment review (ScienceDirect S105687271500361X); NTSS-6 validation
(Bastyr 2005, PubMed 16199253); painDETECT Rasch refinement (PMC5336691); FDA PFDD Guidance 3 +
series (fda.gov); COSMIN content-validity (Terwee 2018, PMC5891557) and COSMIN 2018 manual;
Petrillo 2015 CTT/IRT/Rasch worked examples (*Value in Health*); PROMIS pediatric CAT stopping
rules (PMC12681468). Surfaced-but-unverified leads for the AI-fusion / SaMD half are listed inline
in B2 and must be verified before use. Full research transcript recoverable from the workflow
journal.
