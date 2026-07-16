# The new protocol, graded against the current landscape

**Date:** 2026-07-16 · **Status:** evidence-backed review + grade of the multimodal
Neuropathy Status Index protocol vs. established DPN measurement.
**Companions:** [`biomech-data-streams.md`](biomech-data-streams.md) (the streams),
[`../decisions/2026-07-16-adr-0035-phone-base-adl-health-bridge.md`](../decisions/2026-07-16-adr-0035-phone-base-adl-health-bridge.md)
(phone-base ADLs), [`ai-augmented-protocol-feasibility.md`](ai-augmented-protocol-feasibility.md)
(the development pathway).

> **Grounding & honesty.** The landscape facts and the phone-sensor capabilities below were
> **adversarially verified** (deep-research pass, 2026-07-16: 25 claims, 24 confirmed, 1
> refuted; and the earlier feasibility pass for COSMIN/PFDD). Where a claim did **not**
> survive verification it is labeled. This grades a **v1, non-diagnostic, pre-validation**
> protocol — the grade is of the **design vs. the field**, not a validation result. Not
> clinical or regulatory advice.

## The rubric (as agreed)

Seven criteria: **Coverage** (symptoms ∧ signs ∧ function ∧ QoL) · **Objectivity**
(subjective PRO vs. objective sensor vs. both) · **Frequency/Responsiveness** (episodic vs.
daily curve) · **Multimodal fusion** (single instrument vs. composite index) ·
**Measurement rigor** (COSMIN's nine properties + FDA fit-for-purpose) · **Burden**
(respondent + clinician) · **Real-world validity** (clinic/recall vs. daily life).

## The current landscape (verified)

Every established DPN measure is **validated but siloed** — it covers *one* construct, is
*single-modality*, and is *episodic* (a point-in-time snapshot):

| Instrument | Covers | Reporter | Cadence | Validation (verified) |
|---|---|---|---|---|
| **NTSS-6** | sensory **symptoms** only | patient | episodic | internal consistency / test-retest / construct validity (Clin Ther 2005) |
| **Norfolk QOL-DN** | **QoL** (symptom/small-fiber/large-fiber/autonomic/ADL) | patient | episodic | 47-item PRO, validated n=262 (Vinik 2005) |
| **mTCNS** | clinician **exam** scale | clinician | episodic | inter-rater ICC 0.87 *(its "captures symptoms+signs, max 33" scope claim was **refuted** — treat as an exam scale)* |
| **UENS** | early sensory **signs** | clinician | episodic | 92% sensitivity in one developer cohort *(not independently replicated)* |
| **Monofilament / VPT** | large-fiber **signs** | clinician | episodic | screening; monofilament accuracy is inconsistent (prior pass) |

**Digital biomarkers** (wearable-IMU sway, gait variability, plantar pressure) exist as
*single* objective signals — but whether they are validated and *predictive of falls/
progression* **did not survive verification** in either research pass (an open evidence
gap, consistent with the feasibility doc's Part B2).

**The gap:** no **longitudinal, multimodal composite index** fusing patient-reported
symptoms + objective gait/balance + labs into a single score surfaced in the verified
corpus. ⚠️ *Honest caveat:* this absence was **not affirmatively proven** against a
systematic search — so we claim "none surfaced," not "none exists," until confirmed.

## Phone-sensor reality (verified — shapes the real-world tier's grade)

- **Reliable phone-alone:** walking **speed** (ICC ~0.85–0.93) and **step length**
  (~0.76–0.85). ✅
- **Weak phone-alone:** walking **asymmetry** and **double-support time** (ICC ~0.42–0.58,
  large bias) — advisory or watch-augmented only. ⚠️
- **Android** Health Connect exposes **no gait-quality types** at all — quantity/pace only;
  gait quality needs custom raw-sensor work. ⚠️
- **Biggest caveat:** all these figures are from **healthy adults, not a DPN/impaired-gait
  population** — accuracy in our target users is **unverified**. ⚠️

## The grade

Tiers: **Strong** (leads the field) · **Moderate** · **Emerging** · **Not-yet-established**.

| Criterion | Grade | Why |
|---|---|---|
| **Coverage** | Strong-with-gaps | Symptoms + function (clinical **and** real-world) + physiologic in one measure — broader than any single instrument. **Gaps:** no clinician **sign** exam (monofilament/reflex/pinprick) and only *partial* **QoL** (function proxies, not a Norfolk-style QoL PRO). |
| **Objectivity** | **Strong** | Fuses subjective PRO **and** objective sensor data. Most instruments are one or the other; combining both is uncommon. |
| **Frequency / Responsiveness** | **Strong** (design) | A **daily curve** vs. everyone else's episodic snapshot — the biggest structural advantage for trend detection. *But* responsiveness/MCID are **unproven** for our index. |
| **Multimodal fusion** | **Strong** (design) | A single composite fusing all streams — the differentiating **gap** (none surfaced in the landscape). *Novelty not yet systematically confirmed.* |
| **Measurement rigor** | **Not-yet-established** | v1 uses **hand-set weights**, `validated_instrument: false`, no reliability/validity/responsiveness study. This is the honest weak point — comparators *are* validated; we are not, yet. |
| **Burden** | Moderate | Daily symptoms + daily BioMech gait+balance is **heavier** than a periodic questionnaire. Mitigated by **passive** watch ADLs (zero burden) and future **CAT/IRT** on symptoms, but the daily clinical test is real burden. |
| **Real-world validity** | Moderate→Strong (conditional) | It *has* a real-world tier (phone/watch ADL) — most measures are clinic/recall only. **Conditional on** phone-gait accuracy holding in a DPN population (currently unverified) and leaning on the reliable metrics (speed/step-length). |

### Overall verdict — *leading on design, pending on validation*

The protocol is **ahead of the current landscape on the axes that structurally matter** —
coverage, objectivity, frequency, and multimodal fusion — and it targets a **real gap** (no
longitudinal multimodal DPN composite surfaced). That is a genuine, defensible
differentiation.

But it is **behind on evidence**: it is an **unvalidated v1**, its phone-derived gait
signal is **unproven in the target population**, and its **burden and responsiveness** need
work. In one line: **strong concept, unproven measure.** The comparators are the mirror
image — narrow and episodic, but *validated*.

## What moves each grade up (the roadmap this implies)

- **Measurement rigor → Moderate/Strong:** the COSMIN/PFDD validation sequence (content
  validity → structural → reliability → responsiveness/MCID) from the feasibility doc; move
  from hand-set to **IRT/empirically-derived** weights on real data.
- **Coverage → Strong:** add a light **clinician sign** input (or a validated self-exam
  proxy) and a **QoL** item set; decide whether QoL is in-scope for v1.
- **Real-world validity → Strong:** a **DPN-population** accuracy study of iPhone
  speed/step-length; keep asymmetry/double-support **advisory** until proven; solve the
  **Android gait-quality gap** (raw-sensor pipeline) or scope Android to volume/pace.
- **Burden → Strong:** **CAT/IRT** to shorten the symptom check-in; maximize **passive**
  (watch) capture; make the daily BioMech test as short as clinically valid.
- **Multimodal-fusion novelty → confirmed:** a systematic search to affirmatively document
  that no equivalent composite exists before claiming it in papers/IP.

## Sources (verified this pass)

Apple iPhone mobility whitepaper + WWDC 2021 (metric set, phone-alone); Nature Sci Rep 2023
and WKU IJES 2023 (phone-vs-gold-standard validity); npj Digital Medicine 2024 (Apple Heart
& Movement Study); Android Health Connect data-types docs (gait-quality gap); NTSS-6 (Clin
Ther 2005), Norfolk QOL-DN (Vinik 2005), mTCNS (Bril, PMC2871179), UENS (Singleton 2008).
COSMIN/PFDD rubric + the "no gold-standard composite" gap carry from the feasibility pass.
Full transcript in the workflow journal.
