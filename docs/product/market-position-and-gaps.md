# Market position and feature gaps — quality-first DPN measurement

> **Product strategy synthesis, not clinical, regulatory, or legal advice.** FDA SaMD
> classification, billing compliance, and validation design require qualified expert
> sign-off. Every external claim carries a source; time-sensitive and single-source claims
> are flagged. Built from the internal feature inventory (2026-07-18) + a cited market
> research pass (2026-07-18: 24 sources, 10 verified findings, 3 refuted).

## Bottom line

No incumbent combines ADA-aligned neuropathy assessment, multimodal gait/balance sensing, and
labs/CGM into a **single validated longitudinal trajectory for 60+ patients**. That
combination is the whitespace, and it is where our product already sits structurally. The
market is fragmented into four adjacent clusters that each solve one slice; our differentiator
is the fusion none of them attempts.

The gating weakness is not features — it is **measurement rigor and FDA device status**. The
NSI is today an explainable but *unvalidated* composite with hand-set weights
(`validated_instrument:false`). Reimbursement (RPM/RTM) is a real pathway but legally requires
an FDA-defined device and clinical credibility first; a "reimbursement-first" strategy is
foreclosed by the evidence. So the order is correct: **quality → validation → FDA posture →
reimbursement.** The three features most worth building now all serve that order, not the
reimbursement column.

---

## 1. Competitive landscape — four clusters, no overlap

The market splits into four groups. Each is strong in one dimension and absent in the others;
none delivers a longitudinal multimodal DPN trajectory.

**A. DPN-specific home / point-of-care devices.** Foot-temperature monitoring mats and socks
(Podimetrics SmartMat, Siren socks) and point-of-care nerve screeners (DPNCheck sural nerve
conduction, Neuropad, VPT/biothesiometry). These target **foot-ulcer prevention or a
point-in-time screen**, not longitudinal symptom+function+physiologic tracking. *(FDA status
and reimbursement for these named devices did not fully verify in this pass — flagged as an
open item to confirm before any head-to-head claim; sources were vendor/blog quality.)*

**B. Diabetes self-management apps / PDTs.** Large diabetes platforms focus on glucose,
medication, and lifestyle. Whether any ship neuropathy or foot-complication features today
**did not verify** — treat "diabetes apps largely ignore neuropathy" as a working hypothesis,
and note the fast-follow risk if this whitespace is validated (open question).

**C. Gait / balance / falls-risk digital biomarkers.** The direct incumbents for objective
balance and falls scoring in older adults are validated but single-modality:
- **Kinesis QTUG** (leg-worn wireless IMUs → objective Falls Risk Estimate from an
  instrumented Timed-Up-and-Go; now associated with Linus Health).
- **Zibrio** (force-plate SmartScale, 60-second eyes-open stand at 60 Hz → 1–10 Postural
  Stability score).

  Their honest performance sets our realistic bar: Zibrio's postural score in a prospective
  cohort (N=209) made high-risk individuals ~3× more likely to fall in 12 months, but at
  **sensitivity 64.2% / specificity 59.8% / AUC 0.64** — modest. Wearable-IMU ML fall-risk
  models reach **AUC ~0.75–0.88**. **Do not claim gait metrics are FDA-cleared as diagnostics
  — that was specifically refuted (0–3).**

**D. RPM / RTM plumbing.** Monitoring platforms that bill for clinician review of
patient-generated data. Our own `reimbursed-apps-comparison.md` already maps nine of these
(Limber, OneStep, Exer, Hinge, Sword, Sway, etc.). They provide the *billing rails*; none
provides a DPN measure. We plug into this layer, we don't compete with it.

**The nearest direct analog** is the **Neuropathy Tracker** smartphone self-assessment (PLOS
Digital Health): concurrent validity rho=0.86 but only moderate concordance **CCC=0.69**, all
17 patients self-administered unaided. It proves feasibility of self-administered DPN
measurement **and** marks the validation ceiling a quality-first product must beat (n=17,
Android-only, in-clinic — preliminary, not robust).

---

## 2. Table-stakes features — scored against what we ship

The evidence on what patients (especially 60+) and clinicians actually require, mapped to our
current build. "Have" = shipped; "Partial" = shipped but shallow; "Gap" = not built.

| Table-stakes requirement (evidence) | Us | Notes |
|---|---|---|
| **Usability for 60+**: large fonts, few functions, setup wizards, low-vision/low-dexterity support | **Have** | ADR-0039 enforced by contrast tests; 17px min body, 48px targets. **No onboarding wizard yet** → Partial on setup training. |
| **Clinician endorsement / physician-prescribed distribution** (patients often won't adopt otherwise — 3 studies) | **Partial** | We have a clinician surface + invitations, but distribution is not built around physician prescription. Strategy implication, not just a feature. |
| **Closed clinician feedback loop** (drives both adoption and sustained motivation in 60+) | **Partial** | Clinician panel + patient detail exist (ADR-0012/0016). Missing: alerts/escalation, care-team messaging, real-time surfacing during the encounter. |
| **SMART-on-FHIR PRO integration** (proven, effectively table stakes) | **Have (inbound)** | We *pull* EMR labs via SMART-on-FHIR (ADR-0008/0009). We do **not push** PROs back into the EHR for in-encounter viewing — the demonstrated pattern (JAMIA, 18 sites). This is a gap on the *outbound* half. |
| **HIPAA posture, non-diagnostic framing, data transparency** | **Have** | BAA-gated AI, PHI-free logging (ADR-0021), non-diagnostic notes co-located (ADR-0016), export + deletion (ADR-0031/0027). A genuine strength. |
| **ADA-aligned assessment cadence & modalities** (annual DPN screen; small-fiber temp/pinprick, 128-Hz vibration, 10-g monofilament) | **Gap (mapping)** | Our symptom items are NRS pain + generic numbness; we don't yet *map* our measures to the ADA-recognized modality set or frame cadence around the annual standard. Cheap credibility win. |
| **Accessibility onboarding / caregiver involvement** | **Gap** | No caregiver role, no guided first-run. Both are documented 60+ adoption facilitators. |

**Reading:** we are strong exactly where trust and accessibility live (our deliberate
investment), and thin exactly where the *clinician loop closes* — outbound PRO-to-EHR, alerts,
messaging, and physician-prescribed distribution.

---

## 3. Gaps and whitespace

**Our defensible whitespace (validated by the research):**
- **The multimodal longitudinal trajectory itself.** No incumbent fuses PRO symptoms +
  objective gait/balance + labs/CGM into one over-time measure. Every established DPN
  instrument (NTSS-6, Norfolk QOL-DN, monofilament/VPT) is validated but siloed, episodic,
  single-modality.
- **Between-visit monitoring for a slow-moving complication.** Ambulatory self-assessment
  fills the referral-to-neurology delay and the year-long gap between annual screens
  (single-source, 2–1 verified — directional).
- **Built-for-60+ from the ground up.** Most digital biomarkers are validated *on* older
  adults but not *designed* for their digital-literacy, vision, and dexterity constraints.

**Our gaps relative to the market:**
1. **Measurement rigor** — the NSI is unvalidated with illustrative weights. This is the
   single biggest gap and the prerequisite for everything downstream.
2. **No outbound clinician loop** — no PRO-to-EHR push, no alerts/escalation, no messaging.
3. **No time-capture / RTM operational layer** — no timer, day-counter, or evidence export
   (the unbuilt "Wave 4"), so we cannot yet support billing even when the device question
   resolves.
4. **DPN-specific feature adjacencies we don't touch** — foot-temperature/foot-photo
   monitoring (the Podimetrics/Siren category), medication/titration tracking. These may be
   deliberate scope choices; the recommendation (§5) is to *stay focused* and integrate rather
   than rebuild them.

**What creates durable differentiation** (from the research + our own docs): a **validated
proprietary measure**, a **proprietary longitudinal dataset**, **clinical evidence and
guideline recognition**, and eventually **payer coverage** — in that order. Not an AI-accuracy
claim: the multimodal-fusion moat is a *lead to prove*, not a proven finding, and the ML
fall-risk literature is association-level and unvalidated in a DPN population.

---

## 4. Reimbursement reality (secondary lens)

Confirms the quality-first ordering rather than changing it:
- **RPM/RTM are the realistic near-term pathways**, with hard requirements: the data-
  collection device must meet the **FDA definition of a medical device** (FD&C 201(h) — a
  lower bar than clearance, but a bar); **16 days of data per 30** for 99454/98976/98977; RPM
  (not RTM) needs an **established patient**. RTM uniquely permits self-reported data — the
  better fit for us (already our `reimbursement-analysis.md` conclusion).
- **No general Medicare PDT coverage exists.** It hinges on unpassed legislation (H.R.3288,
  introduced 2025-05-08) that would take years to operationalize *and legally requires FDA
  clearance first*. "Reimbursement-first" is not available as a strategy.
- **The validation bar comes before the money**: peer-reviewed validation and an FDA posture
  precede any reimbursement bet. Our nearest analog sits at CCC≈0.69 feasibility — that is the
  floor to climb from.

---

## 5. Recommendation — must-have / differentiator / defer

Mapped to the gaps in §3, ordered quality-first.

**Must-have now (close credibility + table-stakes gaps):**
1. **Advance measurement rigor.** Map NSI symptom measures to the **ADA modality set and
   annual cadence**; adopt a licensed symptom instrument where numbness needs it (per
   `instrument-licensing-research.md`); stand up the **IRT/CAT groundwork** (roadmap Spec 4) as
   the first real AI lever. This is the moat's foundation.
2. **Close the clinician loop outbound.** Add alerts/escalation and, over time, **PRO-to-EHR
   surfacing** (the JAMIA-proven SMART-on-FHIR pattern) so data reaches the clinician in the
   encounter — the demonstrated driver of both adoption and retention in 60+.
3. **Onboarding wizard + caregiver support.** Both are documented 60+ adoption facilitators
   and cheap relative to their adoption impact.

**Differentiator (build the moat):**
4. **The validated longitudinal multimodal trajectory** — the fusion nobody else attempts;
   requires the proprietary longitudinal dataset to be accumulating *now*.
5. **Fold objective wearable gait/balance into the score** (NSI Function two-tier, Spec 3) with
   honest performance framing (AUC ~0.75–0.88 ceiling; never "FDA-cleared").

**Defer (integrate, don't rebuild):**
6. Foot-temperature/foot-photo monitoring — integrate the incumbent category (e.g. as an EMR/
   device stream) rather than rebuild Podimetrics/Siren.
7. **RTM operational layer** (timer, day-counter, evidence export) — real, but gated behind the
   FDA device-status decision; build it when that resolves, not before.
8. Food logging (V2, already spec'd) — estimation, not measurement.

---

## 6. Phased path and moat bets

1. **Phase 1 — Credibility (now).** ADA-mapped measures, licensed instrument where needed,
   deterministic v1 shipped, dataset accumulating, clinician loop closing. Resolve the **FDA
   device-status ADR** — the one decision everything downstream waits on.
2. **Phase 2 — Validation.** A prospective study establishing reliability/validity/
   responsiveness of the NSI and the DPN→ADL/falls links our evidence docs flag as thinly
   supported (the data we can *own*). Beat CCC≈0.69.
3. **Phase 3 — FDA posture.** SaMD classification / clearance path informed by Phase 2.
4. **Phase 4 — Reimbursement.** RTM-first, once the device question and validation are in hand
   and the operational layer is built.

**The 2–3 durable moat bets:** (a) the **validated proprietary DPN composite** (measurement
science, not sensor ML); (b) the **proprietary longitudinal multimodal dataset** that no
single-modality incumbent can assemble; (c) **guideline-aligned clinical evidence** that earns
recognition and, eventually, coverage.

**Biggest risks:** (1) staying at feasibility-grade validation — the thing that separates us
from Neuropathy Tracker; (2) an unresolved FDA posture blocking both SaMD and billing
indefinitely; (3) a diabetes-platform fast-follow if we validate the whitespace without a data/
evidence moat in place; (4) over-scoping into foot-device or food territory and diluting the
measurement focus that is the actual differentiator.

---

## Sources & honest caveats

Primary/verified: ADA Standards of Care (PMC10725803); Neuropathy Tracker feasibility (PLOS
Digital Health); Zibrio validation (PMC7772994); Kinesis QTUG (vendor + peer-reviewed); IMU-ML
falls reviews (Frontiers in Neurology 2026; medRxiv preprint); 60+ usability reviews
(PMC12464506 JMIR Aging 2025; PMC11751966); SMART-on-FHIR PRO integration (JAMIA 2021); RPM/RTM
billing (HHS telehealth guide); PDT legislation (Congress.gov H.R.3288 + AMCP/ATA/npj Digital
Medicine 2025).

**Flagged:** DPN-specific device details (Podimetrics/Siren/DPNCheck/Neuropad FDA +
reimbursement status) and diabetes-platform neuropathy features **did not verify** — confirm
before any head-to-head claim. **Refuted, do not cite:** gait metrics as FDA-qualified
biomarkers (0–3); "provider-connected apps → larger HbA1c reduction" (1–2); a specific
engagement-decline retention stat (1–2). Reimbursement rules are annual and policy-sensitive;
H.R.3288 is unpassed. The Neuropathy Tracker analog is n=17 preliminary. This synthesis is
strategy input, not regulatory or legal advice.
