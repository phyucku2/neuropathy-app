# AI/ML fusion for neuropathy measurement — what the evidence actually supports

> **Research synthesis, not clinical or regulatory advice.** Final scientific and
> regulatory sign-off rests with qualified experts. Every factual claim below carries its
> source; anything unverified is flagged as such.

## Bottom line (read this first)

The published, peer-reviewed evidence for AI/ML in **diabetic peripheral neuropathy (DPN)**
measurement is **real but early-stage, and it does not yet support the specific product
thesis** of a *validated* multimodal fusion of patient-reported symptoms + wearable
gait/balance + labs. Concretely:

1. **No located study fuses our intended stack.** Every "multimodal" DPN ML study we found
   fuses **imaging** (plantar pressure or ultrasound) with clinical/lab variables — **none**
   fuses self-reported symptoms + wearable IMU gait + labs. The wearable-gait evidence and
   the multimodal-fusion evidence come from **different, non-overlapping studies.**
2. **Almost nothing is externally validated.** Exactly **one** DPN model (LEG-Sys/BalanSens)
   has any external validation — on **n = 42**. A 2025 systematic review included only 15 of
   888 studies (3 externally validated); a 2025 diabetes-risk meta-analysis found **zero ML
   models** externally validated.
3. **No study shows improved patient *outcomes*** — only discrimination metrics (AUC /
   sensitivity / specificity). The gap between "good AUC" and "clinical utility" is unclosed.
4. **Reported accuracies are likely optimistic** — internal-only validation, small cohorts, and
   at least one 100%-accuracy plantar-pressure result on 86 patients that almost certainly
   reflects overfitting.
5. **Two whole questions returned zero verified claims** and remain **unanswered** in this
   pass: the FDA AI/ML-SaMD requirements (GMLP / PCCP / lifecycle), and where a durable moat
   actually forms.

**Implication:** the honest moat is *not* an AI-fusion accuracy claim today — it is the
**deterministic v1 composite + the proprietary longitudinal multimodal dataset** we are
positioned to collect. AI fusion is R&D, not a validated selling point.

**Verification stats:** 5 search angles → 20 sources fetched → 90 claims extracted → 25
adjudicated (25 confirmed, 0 refuted) → 7 findings after synthesis. This pass deliberately
targeted the Part B2/C items that the prior
[feasibility review](./ai-augmented-protocol-feasibility.md) flagged as *surfaced-only,
not verified* — and it confirms that caution was warranted.

---

## Findings

### Multimodal fusion & the DPN ML evidence base

**F1 — No DPN model fuses our intended modalities (high confidence).** Existing "multimodal"
DPN ML fuses imaging + clinical/lab data. *SoleFusion-Net* (late-fusion plantar-pressure CNN
+ structured clinical branch, 504 patients) reports **83%** validation accuracy; an
ultrasound + clinical random-forest (235 patients) reports **test-AUC 0.852** with training
AUCs > 0.9 (a train–test gap indicating optimism). Both are single-cohort, **internal
validation only** — the "accuracy gains" are not shown to generalize, and neither uses
wearable gait or PRO symptom scales.
· [SoleFusion-Net](https://www.nature.com/articles/s41598-026-42207-6)
· [ultrasound+clinical](https://onlinelibrary.wiley.com/doi/10.1002/jum.70237)

**F5 — No study demonstrates improved outcomes, only AUC (high).** Even the largest clean
cohort — an SGBT clinical/lab DPN model (n = 1,544, test-AUC 0.811) — reports only
discrimination + decision-curve net benefit, framing clinical utility as future work. A 2025
systematic review confirms the field measures AUC, not outcomes. This directly answers "does
ML improve DPN outcomes?": **no current evidence that it does.**
· [SGBT model](https://www.frontiersin.org/journals/endocrinology/articles/10.3389/fendo.2025.1614657/full)
· [systematic review](https://link.springer.com/article/10.1186/s12911-025-03201-6)

**F6 — The evidence base is small and methodologically weak (high).** The 2025 DPN ML
systematic review included **15 of 888** studies (all internal validation, only 3 also
external). A plantar-pressure study (86 patients, single center, no control group, 5-fold CV)
reported **100% static accuracy** — a strong overfitting signal, not real-world performance.
A diabetes-risk meta-analysis (65 studies / 97 models) found **91.8% at high risk of bias**
and only 21.6% externally validated — **none of them ML.**
· [systematic review](https://link.springer.com/article/10.1186/s12911-025-03201-6)
· [plantar-pressure 100%](https://www.nature.com/articles/s41598-025-07774-0)
· [diabetes-risk meta-analysis](https://ec.bioscientifica.com/view/journals/ec/14/11/EC-25-0353.xml)

### Wearable gait & balance digital biomarkers (the most credible signal)

**F2 — Wearable IMU biomarkers are the strongest DPN signal, but discrimination is modest and
external validation is tiny (high).** *LEG-Sys/BalanSens* (68 features from a one-minute walk
+ balance test) reached **AUROC 0.80 (95% CI 0.64–0.92)** in a 206-participant development
cohort and was **externally validated on 42 participants** (78.6% accuracy). SHAP flagged
**stride-length variability** and **double-support time** as key features. Caveats: wide CI,
n = 42 external set with 4 false positives, and the headline "89.3% adjusted concordance" is a
**non-standard post-hoc metric that must not be cited as validated performance.** It
classifies DPN *status*, not prospective falls.
· [LEG-Sys/BalanSens external validation](https://karger.com/ger/article-abstract/doi/10.1159/000551704/947544/Development-and-Multicenter-External-Validation-of)

**F3 — Postural sway velocity is an association-level biomarker, not (yet) a validated fall
predictor (high).** A community study (n = 146) found sway velocity discriminated DPN at
**AUC 0.76** and remained an independent predictor alongside diabetes duration. A wearable-IMU
study (n = 85) linked AP/ML sway to *deep* DPN and to fall-risk **scales**. Both are
cross-sectional, single-center, small, and correlate against fall-risk *scales* rather than
prospective fall *events* — **association, not validated prediction.**
· [community study](https://pmc.ncbi.nlm.nih.gov/articles/PMC12128393/)
· [wearable IMU study](https://www.sciencedirect.com/science/article/pii/S0965206X23001055)

**F4 — Sway *complexity* direction is not a reliable biomarker in diabetes (medium).**
High-risk T2DM fallers have shown *increased* sway variability/complexity — contradicting the
"loss of complexity" theory. Treat complexity direction as a **feature-engineering caution**,
not a settled signal.
· [Morrison et al. 2012](https://www.sciencedirect.com/science/article/abs/pii/S0966636211008290)

### Scope-mismatch trap

**F7 — Several prominent "peripheral neuropathy" gait/ML papers are NOT about DPN (high).** A
2025 digital-gait-biomechanics paper studies **inflammatory/hereditary** neuropathies (CIDP,
IgM-MGUS, hereditary) with no diabetic cohort and no ML; a high-AUC (0.93) multimodal
transformer study is **chemotherapy-induced** peripheral neuropathy (CIPN). Neither is DPN
evidence and neither should be cited as such.
· [J NeuroEng Rehabil 2025](https://jneuroengrehab.biomedcentral.com/articles/10.1186/s12984-025-01694-w)
· [CIPN transformer](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12324740/)

---

## What remains UNVERIFIED / open questions

This pass produced **zero surviving verified claims** on two research questions — they are
effectively unanswered here and each needs a dedicated pass against primary sources:

- **FDA AI/ML-SaMD requirements (RQ4).** What an AI-in-the-loop, non-diagnostic measurement
  product must satisfy under the 2025–2026 GMLP guiding principles, the finalized
  Predetermined Change Control Plan (PCCP) guidance, and the AI-enabled device lifecycle
  guidance. (Primary FDA guidance URLs were fetched but no claim cleared verification this
  pass — see the source list in the workflow output.)
- **Durable competitive advantage (RQ5).** Whether moats for digital-biomarker / AI-measurement
  companies actually form around a proprietary longitudinal dataset, a validated composite
  index, adaptive measurement, or regulatory/data network effects — versus these being
  untested hypotheses.

Two narrower gaps also remain open:

- **Incremental value.** No head-to-head evidence that *adding* wearable/PRO modalities to a
  clinical-lab baseline yields a measurable AUC or outcome lift.
- **Prospective prediction.** All wearable-biomarker evidence is cross-sectional/associational;
  none prospectively predicts fall *events* or progression over time.

---

## Implications for the product & the Fornari white paper

- **Lead with the deterministic v1 composite and the dataset, not an AI-accuracy claim.** The
  defensible, honest moat is the *proprietary longitudinal multimodal dataset* we can collect
  and the *validated composite index* we can build — not a fusion model the literature hasn't
  yet validated.
- **Position AI fusion as R&D**, explicitly pending our own prospective validation. Do not let
  it read as a shipped capability.
- **Do not cite the weak/overfit numbers** (100% plantar-pressure accuracy, "89.3% adjusted
  concordance," high-AUC CIPN/CIDP studies) in any external, investor, or clinical document.
- **Wearable gait/balance is the most credible objective signal** — worth building on, but
  frame it as association-level and unvalidated in DPN until we validate it ourselves.
- **Run the dedicated FDA (RQ4) + moat (RQ5) research pass** before any regulatory or
  fundraising claim depends on those answers.

---

*Generated from an adversarially-verified research pass (5 angles, 20 sources, 25 claims
adjudicated, 7 findings). Companion to [`ai-augmented-protocol-feasibility.md`](./ai-augmented-protocol-feasibility.md),
which flagged these exact items as unverified; this review closes part of that gap.*
