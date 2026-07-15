# Brainstorm — Clinical-grade "Neuropathy Status Index" (a non-diagnostic composite)

- **Date:** 2026-07-15
- **Facilitator note:** This brainstorm applies **all 17 mandatory lenses** from CLAUDE.md §6
  (none skipped; where a lens has nothing materially new it says so) plus three
  topic-specific lenses the subject warrants (biostatistics/psychometrics, health
  economics, ethics/health-equity).
- **Builds on / supersedes:** the discarded local "30 Day Score" work — its decision record
  **ADR-0033** (composite *function-only* score) is superseded by the ADR this brainstorm
  forces (**ADR-0034**). References the trajectory engine (ADR-0003), the non-diagnostic
  posture (ADR-0016), the locked trajectory contract + AA-contrast locks (ADR-0015), the
  daily check-in (ADR-0029/0030), and the research-grade data standard (ADR-0006).
- **Cross-reference (regulatory):** `docs/compliance/gap-register/fda.md` — the trajectory
  algorithm is flagged **unvalidated**; the composite index below leans *further* toward an
  interpretive/SaMD output and inherits that open question. Nothing here is a regulatory
  determination or a validated clinical claim.

> **Honesty banner (applies to the whole document).** "Clinical-grade" here means **built to
> clinical measurement standards** — validated instruments, transparent scoring, research-grade
> data integrity, an explicit validation roadmap. It does **NOT** mean *clinically validated*.
> The Neuropathy Status Index is a **non-diagnostic v1 index, pending clinical validation.**
> Every instrument description below that we are not 100% certain of is marked
> **"confirm against source."** No psychometrics are invented; where a number would be a
> clinical cut-point it is marked **illustrative / pending validation**.

---

## 1. The construct

**Neuropathy Status Index (NSI) — a single 0–100 figure summarizing a patient's current
peripheral-neuropathy *status* across three health domains, higher = better health.**

It is deliberately **symptom-forward**: what a neuropathy patient actually experiences (pain,
numbness/paresthesia) carries the most weight, function second, and the slow-moving
physiologic driver (glycemic control) least. It is **not** a diagnosis, a disease-severity
stage, a fall-risk score, or an ulcer-risk score. It is a communication and trend artifact
that supports — never replaces — clinical judgment and the physical exam.

Two numbers are surfaced, and they must never contradict:

1. **The Index (0–100)** — the weighted composite, anchored to a real **"as of" date**.
2. **A 30-day delta** — the change in the *composite itself* over ~30 days, rendered as a
   direction **word** (improving / steady / declining) plus a glyph plus the point
   difference. **The composite's own delta is the single source of truth for direction.**

Separately (and never mixed into the health number) an **at-a-glance Confidence indicator
(High / Medium / Low)** tells the reader how much to trust the Index given how complete and
fresh the data behind it is.

### Why a composite at all, and why *this* shape

The engine already fits a per-signal least-squares line and judges each signal's direction
(`backend/app/trajectory/`), but it composited nothing into a single glanceable status.
Clinicians and patients asked for one figure. The discarded ADR-0033 answer was *function-only*
(labs excluded, symptoms not yet captured) and — critically — it kept the **card color keyed to
the multi-signal `direction` vote while the arrow was keyed to the score's own delta**, so the
two could point opposite ways. That contradiction is the central defect this design removes
(see §5 and §6).

---

## 2. Domain → sub-measure → instrument → data source → normalization/direction

**v1 weighting (LOCKED by the owner): Symptoms 45% · Function 40% · Physiologic 15%.**

| Domain (weight) | Sub-measure | Instrument (anchor) | Data source | Normalize to 0–100 (higher = better) | Direction / polarity |
|---|---|---|---|---|---|
| **Symptoms — 45%** | Neuropathic pain | **NTSS-6** pain descriptor items (burning, aching/tightness, lancinating/shooting) — *confirm exact item set & scoring against source* | Daily check-in (patient-reported) | Map instrument raw range → 0–100, then **invert** | **Invert** (higher raw symptom = worse health) |
| | Numbness / paresthesia | **NTSS-6** numbness + prickling/tingling items (± allodynia item) — *confirm against source* | Daily check-in | Map → 0–100, then **invert** | **Invert** |
| | (optional, v1.x) Pain intensity/interference read | **PROMIS Pain Intensity** and/or **Pain Interference** short form — T-score metric (~mean 50, SD 10; *confirm calibration & recall window against source*) | Daily/periodic check-in | Map a defensible clinical T-range → 0–100, then **invert** | **Invert** |
| **Function — 40%** | Balance | BioMech balance score / postural sway | BioMech report (objective; `document_imported` v1, ADR-0014) | Scale to 0–100; sway metrics inverted | Balance score higher = better; **sway inverted** |
| | Gait | BioMech gait speed / step-time symmetry | BioMech report (objective) | Scale to 0–100 | Higher = better |
| | ADLs | **PROMIS Physical Function** short form and/or **Katz ADL** (0–6) / **Lawton IADL** / **Barthel** (0–100) — *confirm item sets against source* | Daily check-in; **EMR when connected** | PROMIS T-range → 0–100; Katz 0–6 → ×100/6; Barthel already 0–100 | Higher = better |
| **Physiologic — 15%** | Glycemic control | **HbA1c** glycemic-control bands (ADA-informed; **illustrative, pending validation**) | Labs (EMR / patient-confirmed upload) | Map HbA1c% → banded 0–100 | **Invert** (higher HbA1c = worse) |
| | *(future)* B12 sufficiency | Serum B12 | Labs | in-range-is-better mapping | in-range (future, **not in v1 score**) |
| | *(future)* Renal function | eGFR | Labs | scale to 0–100 | higher = better (future, **not in v1 score**) |

**Composite:** normalize every present sub-measure to the common 0–100 "higher = better" metric,
average within each domain to a domain score, then combine domain scores with the 45/40/15
weights. **When a whole domain is absent, renormalize the weights across the domains that ARE
present** (do not impute an absent domain as 0 — that would fabricate a false alarm). Renormalizing
changes what the number *means*, which is exactly why the **Confidence indicator** exists and
must degrade (§4). The 30-day delta is the change in this composite computed the same
deterministic way the engine already fits a line (noise threshold applies, so wobble is not
called a trend).

**Directionality rule (applies everywhere):** pain, numbness/paresthesia, HbA1c, and postural
sway all have **higher raw = worse**, so they are **inverted** during normalization. After
normalization every contributor speaks the same language: **higher = better health.** This is
what lets a single composite delta be coherent.

---

## 3. What is deliberately NOT in the number: adherence → Confidence, not health

**Adherence and "BioMech daily completion" do NOT enter the Index.** They drive only the
separate **Confidence / data-completeness indicator (High / Medium / Low)**.

**Why folding engagement into a health number is misleading.** Engagement measures *how much
data we have and how much to trust it* — not *how the patient's neuropathy is*. Conflating the
two makes the number uninterpretable and can invert its meaning: a deteriorating but diligent
patient would have their decline *masked* by a high-adherence bonus (false reassurance — the
dangerous direction for an insensate-foot population), while an improving but light user would be
*penalized* for not checking in. A health index must move only with health. Keep the axes
orthogonal: the **Index** answers "how is the neuropathy status?"; the **Confidence indicator**
answers "how much should you trust this Index, given the data behind it?"

**Confidence model (High / Med / Low) — two inputs:**

- **Domain coverage** — how many of the three domains have at least one *usable, fresh*
  measure. Three domains fresh → strong; one domain only → weak (and the number is a renormalized
  partial view).
- **Data recency** — the age of the newest contributing datum, judged against a
  **domain-appropriate freshness window** (symptoms are daily and stale within days; HbA1c is a
  ~90-day integral and "fresh" for far longer). The existing engine already has the primitives:
  `FRESH_WITHIN_DAYS` and `STALE_AFTER_DAYS` in `backend/app/trajectory/engine.py`.

Illustrative banding (pending validation): **High** = all three domains present and within their
freshness windows; **Medium** = two domains, or minor staleness; **Low** = one domain, or
material staleness/missing data. Adherence streak and BioMech daily completion are *inputs to
this indicator only*.

**Freshness / "as of" honesty.** A prior review found the score rendered stale data as
confidently fresh. The Index therefore carries an explicit **`as_of` date** = the effective date
of the newest contributing observation (never wall-clock "today"). If that date is older than the
domain-appropriate window, Confidence degrades and the UI must *say* the data is old — a stale
Index is never dressed up as current, and `as_of` is always shown next to the number.

---

## 4. The 17 mandatory lenses (§6) — none skipped

**1. Physician (neurology / endocrinology / podiatry / primary care).** The symptom-forward
weighting has face validity: patients present with pain and numbness; NTSS-6 is a recognized DPN
symptom instrument clinicians will find familiar. Cautions: (a) the Index is **not** a substitute
for the exam — 10 g monofilament, 128 Hz vibration, ankle reflexes, and where indicated NCS remain
the clinical anchors; (b) *podiatry* — worsening **numbness** raises foot-ulcer risk even when the
composite is flat or improving, so per-domain (and per-symptom) visibility must never be hidden
behind the single number; (c) *endocrinology* — HbA1c is a ~3-month integral that moves slowly, so
its 15% weight and slow cadence are appropriate, and the Index must not imply neuropathy is
reversible by glycemic control alone; (d) glycemic bands must be individualized (ADA targets are
patient-specific), so the banded mapping is **illustrative pending clinical sign-off**. A physician
should own the final normalization cut-points.

**2. Patient.** One 0–100 with a plain-word direction is glanceable and motivating, but a single
number risks over-simplification and false reassurance/alarm — mitigated by the direction *word*,
the `as_of` date, the Confidence indicator, and the "talk to your care team" framing already in
the product. Burden matters: NTSS-6 is short, but stacking a second pain instrument daily could
push the check-in past what patients will sustain — consider a lighter daily core with a periodic
fuller instrument (see §5). Patients must not be able to "game" the number, and it must never read
as a grade of the patient.

**3. BioMech Health (client/licensee).** The Function domain (40%, the second-heaviest) leans on
BioMech balance/gait — an objective anchor that fits their hardware value proposition and the
existing PDF ingest (ADR-0014). This honors their "function front-and-center" brief while
respecting the owner's locked symptom-forward weighting. Note two constraints already on record:
BioMech **daily completion is adherence, not health** (Confidence only), and BioMech's own FDA
device status is an external dependency (gap register). The deferred V2 device API/SDK would lift
provenance from `document_imported` to `device_measured` and materially strengthen both the Index
and any RTM claim.

**4. Apple developer (iOS).** No new native surface in Phase 1 beyond added check-in fields; the
offline check-in queue (ADR-0030) already covers submission. VoiceOver must announce the Index,
the direction **word**, the delta, the `as_of` date, and the Confidence level as one coherent
utterance; Dynamic Type must not clip the number. HealthKit is a *future* physiologic/activity
source, not v1. Any embedded instrument must clear licensing before it ships in a build.

**5. Android developer.** Capacitor Android-first (ADR-0023); the symptom fields reuse the existing
check-in stack, so the delta is a form change plus backend schema, not new plumbing. TalkBack parity
with the iOS accessibility contract. Health Connect is the analogous *future* source. The offline
queue applies unchanged.

**6. HIPAA / privacy.** Instrument responses (pain, numbness, ADL, labs) are PHI: per-user record
isolation, least-privilege, audit on read/write (§5). The Index and its inputs must never appear in
logs/metrics or exports beyond minimum-necessary; observability carries counts/fixed vocab only,
never instrument *values* (consistent with the ADR-0021 PHI-free-by-construction rule). Confidence
and adherence are derived from counts and recency, not from surfaced values.

**7. SOC 2 / security.** Inherits the research-grade integrity already in place (ADR-0006):
ALCOA+, append-only, corrections-as-new-rows, full provenance, dual timestamps. The composite is
**derived** data — recompute it deterministically on read; do **not** persist a mutable rollup as a
source of truth (a stored number drifts from its inputs and invites tampering). No secrets; standard
access controls.

**8. Marketing.** "Neuropathy Status Index" is clear and compelling, but the disease-specific name
sharpens the FDA general-wellness tension already flagged in the gap register (P2). Every surface
must carry **non-diagnostic v1, pending validation**; a claims-control gate must stop drift into
"severity," "diagnosis," or "clinically validated." Marketing must not translate "built to clinical
standards" into "clinically proven" — that claim is earned only by the validation study (§7).

**9. Legal & regulatory (incl. FDA SaMD).** A composite *health-state interpretation* leans further
toward SaMD/CDS than the existing trend view, raising the stakes of the open device question
(gap-register P0/P1). The defensive posture that keeps the non-device option available must hold:
non-diagnostic framing, deterministic and explainable scoring, per-domain transparency (supports the
CDS "independent review" prong), and no directive/diagnostic language — but a **patient-facing**
audience complicates CDS-carve-out eligibility, which only the FDA consultant can judge. Instrument
**licensing** is a legal gate: PROMIS and Katz/Barthel/Lawton are broadly available/public-domain
(*confirm*), while **NTSS-6 and NPSI may carry copyright/permission requirements — confirm licensing
before embedding.** Ship no validated-claim language; owner + FDA-consultant sign-offs gate any
clinical/billing-enabling build.

**10. Accessibility (WCAG 2.2 AA).** This lens forces the central fix. **1.4.1 Use of Color:**
direction must be conveyed in **words + glyph**, never color alone — the old card used color (from a
different source than the arrow) as a primary cue, which both violated 1.4.1 and could contradict the
arrow. **1.4.3 Contrast:** reuse the already-locked hero contrast tokens (ADR-0015). Screen readers
announce Index + direction word + delta + `as_of` + Confidence. The Confidence indicator itself must
be text + icon, not color-only. Plain language (6th–8th grade) for cognitive accessibility.

**11. Payer / reimbursement.** Daily symptom + function capture over ≥N days strengthens the **RTM**
data story (self-reported therapeutic response is explicitly permitted for RTM;
`docs/product/reimbursement-analysis.md` §2). The adherence **days-with-data counter** must be
parameterized to the CY2026 tiers (2–15 / 16–30 days), attributable to real submission events, and —
though it also feeds the Confidence indicator — kept as a **separate, source-attributable billing
fact**, never folded into the health number. The Index itself is a clinical-communication artifact,
not a billable service. FDA device status of our software and/or BioMech still gates any actual RTM
claim.

**12. Data science / ML.** The 45/40/15 weights and equal-within-domain averaging are **a priori /
expert-elicited**, chosen for transparency — **not** derived from data, and honestly flagged as such
(clinically defensible weights should come from validation data; §7). Normalization needs anchored
per-measure ranges; PROMIS T-scores need a defensible clinical mapping (*confirm*), HbA1c needs
banded cut-points (illustrative). Missing-domain handling = renormalize across present domains (never
impute 0). Different cadences are a real hazard: a quarterly HbA1c must not dominate a 30-day delta —
compute the delta at the domain level so a slow domain contributes proportionally. No black-box ML in
v1; explainability first. MCID, responsiveness, ceiling/floor effects are **unknown until
validation.**

**13. Clinical research / validation.** See §7 for the full roadmap. Key point: the composite is
itself a **new instrument** — validating its components (NTSS-6, PROMIS, etc.) does not validate the
*weights, the scoring, or its MCID*. Reliability (test-retest, internal consistency), validity
(content, construct, convergent/discriminant against a reference such as MNSI/UENS/NCS), and
responsiveness/MCID must be established for the composite in the target population before any
"validated" claim. This is the gap-register clinical-evaluation row (row 32).

**14. Caregiver / family.** A single index + direction words + Confidence is caregiver-friendly for
monitoring a family member with DPN. Per-domain visibility lets a caregiver notice worsening numbness
(ulcer risk) even when the composite is steady, and the Confidence indicator flags thin data before
anyone over-reads a wobble. Keep the "discuss with your care team" guidance; avoid alarmist framing.

**15. Agile (operating model / phasing / backlog).** Two phases, each a small set of
one-concern PRs with ADRs (§6). **Phase 1** (validated symptom capture) is additive and independently
valuable — it improves trends and the RTM data story *before* the composite exists, so it de-risks the
work. **Phase 2** (composite + Confidence + card fixes) depends on Phase 1's data. Backlog items:
instrument/licensing review, normalization config, symptom check-in UI + schema, composite scorer,
Confidence model, and the hero-card refactor that removes the multi-signal direction vote.

**16. DevOps (CI/CD, infra, release, observability).** All scoring is pure/deterministic → unit-testable
to the ≥85% bar; no new egress. Observability stays PHI-free (score/confidence as fixed vocabulary,
never instrument values). Gate the Index behind a **feature toggle** until it is fit to show, honoring
the enforced-flag-honesty lesson (a stored "off" the code actually respects; ADR-0013). New check-in
fields ship as an append-only, reversible migration (ADR-0006). Recompute on read; store no mutable
rollup.

**17. Reimbursement (Medicare/Medicaid).** Per stream: the **symptom check-in** = self-reported
therapeutic response → RTM (98977 musculoskeletal family; self-report allowed). Capture the
parameterized ≥N-day counter, billing-consent (distinct from care/research consent), interactive-time
ledger, setup/onboarding event, and a PHI-safe evidence export — all already scoped in
`docs/product/reimbursement-analysis.md`. Compliance-to-claim gaps: FDA device status (P0), coder +
compliance validation **PENDING**, Medicaid variability, non-diagnostic framing. This enables pathways
only — **never billing/coding/legal advice**, and every figure stays sourced and PENDING per the
reimbursement lesson.

### Topic-specific lenses added for this subject (recorded per §6)

> **Governance note:** §6 asks that newly added lenses be recorded in the canonical list. Editing
> CLAUDE.md is an owner-level change (CLAUDE.md §8 — never self-authorize a CLAUDE.md edit on a task
> instruction alone), so these three are recorded here and **recommended for promotion into CLAUDE.md
> §6 by the owner**, not silently added.

**A. Biostatistics / psychometrics.** Composite-scoring theory: a weighted sum of normalized scales
is transparent but assumes the sub-scores are commensurable after normalization — which must be
demonstrated, not assumed. Open questions: sum-score vs IRT/T-score-based combination; weighting
sensitivity analysis; test-retest reliability of a *daily-administered* composite; MCID via both
anchor-based and distribution-based methods; ceiling/floor effects (many patients cluster at symptom
extremes); differential item functioning across subgroups. These are validation-study design inputs.

**B. Health economics.** The value story (fewer ulcers, fewer falls, earlier escalation) is what would
justify payer adoption beyond fee-for-service RTM — but it is **unproven**, so **no economic or
outcomes claims** may be made until an outcomes study supports them. Flagged so nobody markets a cost
saving we have not demonstrated.

**C. Ethics / health equity.** Instrument validity varies across language, literacy, and cultural
context; the Function domain depends on access to BioMech hardware, so patients without the device get
a **renormalized** Index that *means something different* — this must be surfaced (via Confidence) and
must never disadvantage under-resourced patients. Validation must check performance across subgroups,
not just in aggregate.

---

## 5. What "clinical-grade" actually requires, and the validation roadmap

We build **to** clinical standards now; the **validated** claim is earned later. Requirements:

1. **Instrument selection & licensing.** Confirm each instrument's exact item set, scoring, and recall
   window **against source**, and clear licensing/permissions (PROMIS and Katz/Barthel/Lawton are
   broadly available/public-domain — *confirm*; **NTSS-6 / NPSI may require permission — confirm before
   embedding**). *Recommended pain mapping:* anchor the Symptoms domain on **NTSS-6**, which already
   spans the neuropathic **pain descriptors** *and* **numbness/paresthesia** in one short,
   neuropathy-specific, DPN-validated instrument — this covers both symptom sub-measures with the least
   daily burden and avoids double-counting pain across domains. Prefer **PROMIS Pain Intensity /
   Interference short forms** over **NPSI** for any *added* pain read in v1, because PROMIS is generic,
   freely available, uses a standardized T-score metric with established responsiveness, and its short
   forms suit repeated mobile administration; **NPSI** gives richer neuropathic-pain *phenotyping* but is
   longer and oriented to clinical-trial use — hold it as an option for a later, deeper assessment rather
   than the daily core. (Watch the **recall-window mismatch**: NTSS-6 commonly uses ~24-hour recall while
   PROMIS short forms commonly use 7-day recall — reconcile before combining; *confirm windows against
   source*.) Note also that **daily in-app self-administration is itself a modification** of how these
   instruments were validated and must be validated as used.
2. **Psychometrics of the composite.** Reliability (test-retest, internal consistency), validity
   (content, construct, convergent/discriminant vs a reference standard such as MNSI/UENS or NCS where
   available), and **responsiveness / MCID** — established for the *composite*, in the *target
   population*, not just inherited from the components.
3. **A prospective validation study.** Pre-specified construct, gold-standard comparator, target
   population, longitudinal design; analysis plan covering the weighting, missing-domain renormalization,
   cadence handling, and subgroup performance (equity lens).
4. **SaMD / regulatory implications.** An interpretive composite raises the device stakes; the FDA
   consultant must opine on device status and CDS-carve-out eligibility for a patient-facing surface
   before any clinical/billing-enabling ship (gap-register P0/P1). Until then: **non-diagnostic only.**

**Framed honestly:** v1 ships a transparent, well-constructed index built from recognized instruments,
labeled non-diagnostic and pending validation. The word "validated" is used only after step 3.

---

## 6. Decisions this brainstorm forces (→ ADRs)

- **ADR-0034 (this wave):** adopt the Neuropathy Status Index construct — three domains, symptom-forward
  45/40/15 weights, validated-instrument symptom capture, **adherence-as-Confidence** (not in the number),
  **composite-delta-as-single-source-of-truth** for direction, **direction-in-words** (WCAG 1.4.1),
  freshness/`as_of` honesty, and **non-diagnostic v1 + validation roadmap**. **Supersedes ADR-0033's
  function-only score.**
- **Follow-on ADRs (as the build lands):** the concrete instrument + licensing selection and the exact
  normalization cut-points (physician-signed); the Confidence banding thresholds; the check-in schema
  migration; and the hero-card refactor removing the multi-signal `direction` vote from the composite
  surface.

---

## 7. Phased build plan

**Phase 1 — Validated symptom capture (pain + numbness) in the daily check-in.**
Add validated pain and numbness/paresthesia capture (NTSS-6-anchored; instrument + licensing confirmed
against source) to the **real** daily check-in — check-in UI fields *and* backend schema/ingestion,
with correct polarity (pain/numbness inverted) and research-grade provenance (ADR-0006). This is
additive, independently valuable (better trends + a stronger RTM data story) and de-risks Phase 2 by
producing the symptom data the composite needs — even before the composite exists.

**Phase 2 — The weighted composite + Confidence + the card fixes.**
Build the deterministic weighted composite (45/40/15, per-measure normalization, missing-domain
renormalization, domain-level 30-day delta), the **Confidence indicator** (High/Med/Low from domain
coverage + recency; adherence feeds only this), and the **card fixes**: the composite's own delta as the
**single source of truth** (retire the separate multi-signal direction vote for this surface so color and
arrow can never contradict), **direction conveyed in words** + glyph (WCAG 1.4.1), and **`as_of`/freshness**
so stale data can never render as confidently fresh. Feature-toggle the Index until it is fit to show.

---

## 8. Non-diagnostic framing (explicit)

The Neuropathy Status Index is a **non-diagnostic v1 index, pending clinical validation.** It does not
diagnose, stage, treat, or predict disease; it supports clinical judgment and the physical exam, never
replaces them. All existing non-diagnostic disclaimers (ADR-0016 / `NonDiagnosticNote`) co-locate with
every surface that shows the Index or its direction. This posture is consistent with, and
cross-references, `docs/compliance/gap-register/fda.md`, which records the trajectory algorithm as
**unvalidated** and routes the device/SaMD determination to a qualified FDA regulatory consultant.
