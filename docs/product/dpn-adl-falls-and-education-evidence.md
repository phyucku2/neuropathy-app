# DPN → ADLs, falls, and education modules — what the evidence supports

> **Research synthesis, not clinical or regulatory advice.** Every claim carries its source;
> observational-only and single-study findings are flagged, and anything that would need our
> own prospective validation is called out. Companion to
> [`ai-fusion-evidence-review.md`](./ai-fusion-evidence-review.md) and the education framework
> ([ADR-0037](../decisions/2026-07-17-adr-0037-education-modules.md)).

## Bottom line

Diabetic peripheral neuropathy (DPN) **robustly impairs balance, gait, and functional
mobility and substantially raises fall risk** — that direction is well-supported (two systematic
reviews + a 2025 exercise meta-analysis + multiple primary studies). DPN **severity also
correlates measurably** with objective gait/balance metrics, which is what makes a digital
severity-tracking product credible. **But** the quantitative correlation and fall-prediction
figures each rest on **single, small, cross-sectional, often retrospective** studies, and the
direct DPN→ADL link rests on **only three studies** — so this supports an **association narrative**,
not a **validated predictive/diagnostic claim.** For education, **exercise/balance-training is the
only module with strong verified outcome evidence**; DPP, DSMES, digital-delivery, and foot-care
effect sizes **did not clear verification in this pass** and remain open.

**Verification stats:** 5 angles → 23 sources → 98 claims extracted → 25 adjudicated (23 confirmed,
**2 refuted**) → 10 findings. Sources span 2012–2026; the core fall/gait epidemiology is
slow-moving and current.

---

## Part A — DPN → balance, gait, falls, and ADLs

### Balance & gait impairment (well-supported)
- **DPN alters gait and posture consistently** — longer stance phases, shorter steps, slower
  velocity; large functional-mobility deficits (Timed Up-and-Go **17.8 s DPN vs 11.5 s** controls,
  d=2.2). A 2022 review of 34 studies found 29/37 postural-stability studies confirmed the
  association. *(high)*
  [PMC8861804](https://pmc.ncbi.nlm.nih.gov/articles/PMC8861804/) ·
  [PMC12562028](https://pmc.ncbi.nlm.nih.gov/articles/PMC12562028/)
- **The deficit is largest in static/challenged conditions;** some *dynamic* (walking) metrics show
  no significant difference in small samples — likely compensatory adaptation and/or low power
  (n=15/group). Do not generalize the null dynamic result. *(medium)*
  [PMC12562028](https://pmc.ncbi.nlm.nih.gov/articles/PMC12562028/)

### Falls (well-supported direction, single-study magnitudes)
- **DPN raises fall risk ~2.3× vs non-neuropathic diabetics** and up to ~15× vs healthy adults;
  fallers are far more likely to have polyneuropathy. The fold-figures are **single-study narrative
  estimates, not pooled** — cite as such. *(high)*
  [PMC12069999](https://pmc.ncbi.nlm.nih.gov/articles/PMC12069999/) ·
  [PMC8861804](https://pmc.ncbi.nlm.nih.gov/articles/PMC8861804/) ·
  [PMC11625983](https://pmc.ncbi.nlm.nih.gov/articles/PMC11625983/)
- **Diabetes itself raises fall risk ~64%** (pooled RR 1.64, 6 cohorts, n=14,685), higher with
  insulin (RR 1.94) — but the "dose-dependent" reading conflates severity with treatment/hypoglycemia.
  *(high)* [Yin 2016, Age & Ageing](https://academic.oup.com/ageing/article/45/6/761/2499230)

### Severity ↔ objective-metric correlation (the product-relevant part)
- **Postural sway velocity rises stepwise** with DPN status (healthy 0.73 → diabetic-no-DPN 0.95 →
  DPN 1.20 cm/s), discriminates DPN at **AUC 0.76** (sens 68%, spec 86%), and correlates with
  nerve-conduction (r ≈ 0.41–0.44). Single cross-sectional study, n=146 (22 DPN), **moderate** (r≈0.4)
  correlations, categorical status not graded severity. *(medium)*
  [PMC12128393](https://pmc.ncbi.nlm.nih.gov/articles/PMC12128393/)
- **Each 1-point MNSI severity rise → +23% recurrent-fall odds** (OR 1.23, 95% CI 1.08–1.40);
  self-reported balance problems more than double fall odds (OR 2.65). Cross-sectional/retrospective,
  modest sample — "associated," not "prospectively predicts." *(medium)*
  [PMC12758703](https://pmc.ncbi.nlm.nih.gov/articles/PMC12758703/)
- **Validated functional screens flag risk in DPN:** 20% exceeded the TUG 13.5 s fall-risk threshold;
  each 1-unit higher balance confidence (ABC scale) → 9% lower fall odds (OR 0.91). Single
  cross-sectional cohort, no comparator. *(medium)*
  [PMC7644813](https://pmc.ncbi.nlm.nih.gov/articles/PMC7644813/)
- **Caveat against over-extrapolation:** in the MOBILIZE Boston cohort, *idiopathic* neuropathy
  raised falls but *known-disease* (incl. diabetic) neuropathy did not reach significance — a reason
  not to import monofilament fall-risk figures wholesale. *(medium)*
  [PMC3323485](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3323485/)

### The direct DPN → ADL link (the weakest link)
- **All identified ADL studies found decreased ADLs with DPN** (ADL restriction tied to depressive
  symptoms and neuropathic pain) — **but only three such studies exist**, and the review itself says
  the overall DPN→ADL impact "remains unknown." This is the endpoint a product would target, and the
  thinnest evidence — it **warrants our own validation.** *(medium)*
  [PMC8861804](https://pmc.ncbi.nlm.nih.gov/articles/PMC8861804/)

**Do NOT cite (refuted during verification):** an OR=17.41 neuropathy-fall figure, and gait
effect sizes of d=3.9 / d=5.3 — these failed adjudication.

---

## Part B — Education modules

- **Exercise / balance-training education — strongest verified evidence.** 2025 systematic
  review/meta-analysis (23 studies, older adults with DPN): **gait speed +0.08 m/s** (95% CI
  0.05–0.11) and **muscle strength SMD 0.76** (0.19–1.33), both significant. Postural-control (sway)
  benefit was **not** significant overall — so hedge any balance/sway-improvement claim. *(high)*
  [PMC12069999](https://pmc.ncbi.nlm.nih.gov/articles/PMC12069999/)

- **DPP, DSMES, digital-delivery, and foot-care education — UNVERIFIED in this pass.** No confirmed
  claim surfaced on DPP magnitude (the commonly-cited ~58% diabetes-incidence reduction is
  **prevention in pre-diabetes**, not treatment of established neuropathy), DSMES glycemic/outcome
  effects, app-vs-in-person non-inferiority, or foot-care education reducing ulcers/amputations.
  These are **plausible and standard-of-care**, but their effect sizes are **not established by this
  evidence set** — each needs a dedicated verification pass before any is claimed as evidence-backed.

---

## Implications for the product & the white paper

- **The correlation is real enough to *narrate*, not yet to *predict*.** Credible claim: "DPN is
  associated with worse balance/gait and higher fall risk, and severity tracks objective sway/gait
  metrics." Off-limits until we validate: any per-patient fall *prediction* from our metrics.
- **Frame severity as *status*, not graded severity,** except the MNSI-score finding — be precise.
- **The white-paper opportunity is the gap:** the direct DPN→ADL link (3 studies) and prospective
  metric→fall/ADL prediction are exactly what a 213-clinic longitudinal study could *own*.
- **Module priority (evidence-first):** lead with **exercise/balance training** (strongest verified
  outcomes) and keep **foot care** as a standard-of-care companion whose ulcer/amputation evidence we
  should verify in a dedicated pass before quoting numbers.
- **Never import DPP prevention evidence** as if it treats established neuropathy.

*Open items for a follow-up pass:* DPP/DSMES magnitudes and their limits in an already-diabetic
population; app-vs-in-person education non-inferiority; foot-care education ulcer/amputation effect;
and whether our specific digital metrics (sway velocity, stride-length variability, double-support)
predict falls/ADL decline **prospectively** — the validation the product must own.
