# PRO instrument licensing — research findings & recommendation

**Question:** for a *commercial* digital-health app tracking neuropathy **pain + numbness/paresthesia**
(and function), what are the licensing terms of the candidate validated instruments, and what
is the lowest-friction defensible instrument set?

> **Not legal advice — background research to inform a decision.** Final licensing sign-off
> rests with each rights-holder and your counsel. Produced by a multi-source, adversarially-
> verified research pass (72/75 verified claims confirmed, 70 at high confidence); items that
> could not be verified are flagged. Confirm every commercial term directly with the
> rights-holder before relying on it.

## TL;DR

- **"Validated instrument" almost always means "licensed instrument."** Of the strong
  neuropathy PROs, the ones that cover **numbness** (NTSS-6, MNSI) are proprietary and need a
  **negotiated commercial license** with terms we could not verify (get a quote).
- **PROMIS is NOT simply "free for commercial use"** (correcting an earlier statement in this
  project). It is free only for **individual/non-commercial** use; a commercial app must obtain
  **written permission from HealthMeasures** and, for electronic administration, **HEAP**.
  English measures typically carry no royalty, but **permission is still required**; non-English
  translations cost **$1,000 per measure per language**.
- **Numbness is the hard gap.** NRS and PROMIS pain measures, and even NPSI, do **not** capture
  numbness (a *negative* sensory symptom) — NPSI's paresthesia items are *positive* phenomena
  (tingling/pins-and-needles). Only the DPN-specific batteries (NTSS-6, MNSI) explicitly cover
  numbness.
- **What we ship today needs no license** (NRS-style pain + a generic numbness severity item,
  stored `validated_instrument: false`). The licensing question only arises when you adopt a
  *named validated* instrument.

## Findings by instrument

### NTSS-6 (Neuropathy Total Symptom Score-6)
- **Origin / likely rights-holder:** Bastyr, Price, Bril; MBBQ Study Group; *Clinical
  Therapeutics* 2005;27(8):1278-94 — authors affiliated with **Eli Lilly** (Lilly Research
  Laboratories). Industry-originated; the self-administered version + translations were
  developed by **Mapi** (now Mapi Research Trust / ICON). [PubMed](https://pubmed.ncbi.nlm.nih.gov/16199253/),
  [Clinical Therapeutics](https://www.clinicaltherapeutics.com/article/S0149-2918(05)00150-5/abstract),
  [ISPOR SA-version](https://www.ispor.org/heor-resources/presentations-database/presentation/ispor-eighth-european-congress/use-of-the-self-administered-neuropathy-total-symptom-score---6-ntss-6-sa-in-an-international-study)
- **Licensing route:** listed on **ePROVIDE / Mapi Research Trust**. **The commercial vs.
  academic terms, fees, and named copyright holder could NOT be read** (the ePROVIDE page renders
  client-side; not in fetched HTML) — **must be obtained by contacting Mapi/ePROVIDE.**
  [ePROVIDE NTSS-6](https://eprovide.mapi-trust.org/instruments/neuropathy-total-symptom-score-6-items),
  [ePROVIDE terms](https://eprovide.mapi-trust.org/page/terms-and-conditions-of-use)
- **Fit:** self-report; covers **numbness/insensitivity + prickling/tingling + burning + aching +
  sharp/shooting + allodynia** (i.e., numbness AND pain); a modified SA form uses a **7-day
  recall**, 4-point scale, 0–21 score — suited to repeated administration. Validated (n=205, 10
  centers; Cronbach's α > 0.7; ICC > 0.9). [IASP 2024 content-validity](https://posters.worldcongress2024.org/poster/content-validity-of-the-neuropathy-total-symptom-score-in-painful-diabetic-peripheral-neuropathy/),
  [mNTSS-6-SA 2025](https://www.tandfonline.com/doi/full/10.2147/JPR.S539056)
- **Verdict:** the single best fit for your exact domains, but **proprietary + terms unverified.**
  Requires a Mapi/ePROVIDE commercial license.

### PROMIS (Pain Intensity, Pain Interference, Physical Function)
- **Rights-holder / steward:** **HealthMeasures / Northwestern University** (NIH-funded).
- **Commercial terms (the important correction):**
  - Free of licensing/royalty fees **only** for **individual research or individual clinical
    use** — "non-commercial" is defined as US tax-exempt / not-for-profit entities; **a for-profit
    product does not qualify.**
  - **Commercial users must obtain permission** from HealthMeasures to use/reproduce/distribute
    **any** instrument, regardless of purpose.
  - Integrating into a proprietary app / CAT / web portal for data collection needs **written
    approval, even for a single use**; electronic administration by commercial users needs
    **HEAP** (HealthMeasures Electronic Administration Permission — permission letter + screenshot
    review).
  - Software-integration fees vary by platform/instances/language; **non-English translations
    are $1,000 per measure per language.**
  - [Terms of Use](https://www.healthmeasures.net/images/PROMIS/Terms_of_Use_HM_approved_1-12-17_-_Updated_Copyright_Notices.pdf),
    [Software pricing](https://www.healthmeasures.net/implement-healthmeasures/pricing-for-software-applications),
    [Obtain & administer](https://www.healthmeasures.net/explore-measurement-systems/promis/obtain-administer-measures)
- **Fit:** self-report; short forms + CAT; mobile-friendly. Pain Interference covers how pain
  hinders activities/sleep; Physical Function covers function. **Does not have a numbness item.**
  [APTA PROMIS-PI](https://www.apta.org/patient-care/evidence-based-practice-resources/test-measures/patient-reported-outcomes-measurement-information-system-pain-interference-promis-pain-interference-promis-pi)
- **Verdict:** low *fee* for English measures, but **not permission-free** for a commercial app —
  budget for a HealthMeasures permission + HEAP process. Best-in-class for **pain interference +
  function**, not numbness.

### NRS 0–10 (numeric rating scale, pain intensity)
- A generic single-item scale in universal use; **not covered by this research pass** (no
  instrument-specific licensing claim surfaced). Generally treated as non-proprietary, but
  **confirm** there is no specific copyrighted version you'd be copying. Already what the app
  uses for pain.

### MNSI (Michigan Neuropathy Screening Instrument)
- **Rights-holder:** **University of Michigan** (also listed on ePROVIDE). The patient
  questionnaire **does cover numbness**. [U-M patient PDF](https://medresearch.umich.edu/sites/default/files/2025-07/MNSI_patient.pdf),
  [ePROVIDE MNSI](https://eprovide.mapi-trust.org/instruments/michigan-neuropathy-screening-instrument)
- **Commercial terms:** U-M licenses copyright-protected material via **case-by-case negotiated
  terms** (license fees, royalties, milestones, sometimes equity) — no fixed public fee; process
  = contact U-M licensing, NDA, optional Option Agreement, then License Agreement.
  [U-M license process](https://innovationpartnerships.umich.edu/industry/license-process/)
- **Fit caveat:** MNSI is a **screening** instrument (questionnaire + clinical exam), not a daily
  symptom-severity PRO — a fit mismatch for a daily tracker, though its numbness items are useful.

### NPSI (Neuropathic Pain Symptom Inventory)
- Bouhassira et al., *Pain* 2004; self-administered; 5 dimensions, 0–10 scales, **24-hour recall**
  (good for daily/mobile). Listed on ePROVIDE. [PubMed](https://pubmed.ncbi.nlm.nih.gov/15030944/),
  [ePROVIDE NPSI](https://eprovide.mapi-trust.org/instruments/neuropathic-pain-symptom-inventory)
- **Important nuance (verified correction):** NPSI's paresthesia/dysesthesia items are **tingling
  / pins-and-needles (positive** sensory phenomena) — it does **NOT** capture **numbness** (a
  *negative* phenomenon). So NPSI ≠ a numbness measure.
- **Licensing:** terms not stated in the validation article; distributed via ePROVIDE — confirm
  commercial terms with Mapi.

### Also noted (not recommended for this use)
painDETECT (PD-Q), DN4, LANSS — neuropathic-pain *screening* questionnaires (via IQVIA/ePROVIDE),
proprietary and screening-oriented; a 2025 review notes they can't cleanly distinguish
neuropathic from nociplastic pain. Not a fit for daily symptom tracking.

## Recommendation

**Capture the domains with the lowest-friction defensible set, and treat numbness as the one that
may need a license:**

1. **Pain intensity — NRS 0–10** (generic, in use; confirm non-proprietary). ✅ no license.
2. **Pain interference + Physical function — PROMIS short forms**, obtaining **HealthMeasures
   commercial permission + HEAP** (English measures are typically no-royalty; the cost is process,
   not fees). Strong for validation and payer conversations.
3. **Numbness — the deliberate decision point:**
   - **(a) License NTSS-6** via **Mapi/ePROVIDE** if you want one validated instrument that
     covers numbness *and* pain in a DPN-specific battery (get a written commercial quote — terms
     unverified here). This is the most fit-for-purpose and the strongest for a validation study.
   - **(b) Keep a generic numbness-severity item** (NRS-style, non-proprietary, as today) and
     validate the *composite* empirically — zero licensing, but "numbness" is then a home-grown
     item, not a named validated measure.
   - MNSI's numbness items are an option but it's a screening tool with a negotiated U-M license —
     a weaker fit for daily tracking.

**Bottom line:** for a **launch on a budget**, ship **NRS pain + PROMIS (interference + function,
with HealthMeasures permission) + a generic numbness item**, and **request a Mapi/ePROVIDE quote
for NTSS-6** in parallel — adopt NTSS-6 for the numbness domain only if the commercial terms are
acceptable, since it is the one instrument that cleanly covers your numbness requirement and is
DPN-validated. Nothing here changes what the app captures today; it's a swap when you decide.

## Immediate next actions (owner)
1. **Email Mapi Research Trust / ePROVIDE** for the NTSS-6 commercial license terms & fee (and,
   separately, NPSI/MNSI if of interest).
2. **Start the HealthMeasures commercial-permission + HEAP** process for the PROMIS measures you'd
   use.
3. Have **counsel** confirm any agreement and the "may we name the instrument / reproduce items"
   scope before it ships in a commercial product.

## Sources
Key primary/authoritative sources consulted (full list in the research transcript): HealthMeasures
Terms of Use & software pricing; ePROVIDE (Mapi Research Trust) instrument + terms pages for
NTSS-6 / MNSI / NPSI; PubMed/Clinical Therapeutics for NTSS-6 (Bastyr 2005); *Pain* (Bouhassira
2004) for NPSI; University of Michigan Innovation Partnerships license process + MNSI patient PDF;
APTA and NIH CDE for PROMIS Pain Interference.
