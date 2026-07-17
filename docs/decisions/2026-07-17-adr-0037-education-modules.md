# ADR-0037 — Evidence-linked education modules (DPP/DSMES-style)

- **Status:** Proposed
- **Date:** 2026-07-17
- **Relates to:** ADR-0006 (research-grade Observations), ADR-0013 (enforced feature toggles),
  the NSI composite (ADR-0034), and the data-streams work. The evidence base is in
  [`docs/product/dpn-adl-falls-and-education-evidence.md`](../product/dpn-adl-falls-and-education-evidence.md)
  (DPN→ADL/falls correlation + module evidence) — this ADR defines the *framework*; that review
  supplies *which modules* have outcome evidence and *what claims* are defensible.

## Context

Neuropathy management is substantially a **self-management** problem: glycemic control, daily
foot care, fall prevention, and balance/strength activity are the main modifiable levers on
progression and on the ADL outcomes we measure. Structured education programs exist and are
proven at the population level — the **CDC National Diabetes Prevention Program (DPP)** and
**Diabetes Self-Management Education and Support (DSMES)**. Adding education to the app would:

1. give patients a reason to return daily (engagement is what feeds the longitudinal dataset the
   product's value depends on), and
2. plausibly move the very ADL/function outcomes the NSI tracks.

But education about a disease is also where a non-diagnostic wellness product is most tempted to
drift into **individualized medical advice** — which would change the app's regulatory posture and
violate the non-diagnostic invariant. This ADR sets the guardrails before we build.

**Framing correction (important).** The DPP is about *preventing* diabetes in pre-diabetes; our
users mostly **already have** diabetes + neuropathy. We borrow the DPP's proven **structure**
(curriculum, tracking, goals, coaching cadence) but the clinically-matched **content** is
**DSMES** — self-management, not prevention. Content is drawn from **publicly available** curricula
(CDC PreventT2 / DSMES national standards), not licensed instruments.

## Decision

Add a **closed, versioned, clinician-reviewed registry of education modules**, surfaced in a new
non-diagnostic "Learn" area, opt-in and progress-trackable, with the same enforced-toggle and
research-grade-provenance discipline the rest of the app already uses.

- **Content model.** A module is **static, authored, human-reviewed** content in a closed registry
  (like the metric/directionality registries) — an id, version, topic, evidence citations, and
  reading blocks. **No runtime LLM generation of medical content** (a hallucinated foot-care
  instruction is unacceptable); any AI is an *authoring aid*, and every module is
  **clinician-reviewed before it ships**. Each module carries its **source citations** (guideline /
  trial), so claims are traceable — the same honesty posture as the rest of the repo.
- **General, not individualized.** v1 modules are **general disease education** for everyone —
  *not* personalized treatment recommendations, dosing, or "you should do X" directed at the
  individual's data. This is the line that keeps the feature **non-device / non-diagnostic**
  (general health education is outside FDA device regulation; individualized clinical direction is
  not). Personalization/coaching is explicitly deferred (see below) pending an FDA-consultant
  opinion.
- **Opt-in + progress tracking.** Reuse the ADR-0013 pattern: a new enforced capability
  (e.g. `education`, default **off**). Module views/completions are recorded as **PHI-free**
  progress (append-only, counts/ids/timestamps only — never health values), so we can show a
  patient their progress and study engagement, without turning education into a health record.
  Completion is **not** an NSI input (it is not a clinical measurement).
- **Delivery.** A `Learn` surface lists available modules, gated by the capability + consent, each
  page carrying the standard **non-diagnostic disclaimer** and a "not a substitute for your care
  team" line. Modules can *link out* to the check-in / trends where relevant (e.g. a foot-care
  module next to a foot-check reminder) but never present themselves as advice tailored to the
  patient's readings.
- **First module (evidence-informed).** The cited research pass has now run. **Exercise /
  balance-training education has the strongest *verified* outcome evidence** in DPN (2025
  meta-analysis, 23 studies: gait speed +0.08 m/s, strength SMD 0.76) and is the evidence-first
  choice. **Daily foot care** remains a standard-of-care, high-impact companion (ulcer→amputation is
  the most preventable ADL catastrophe), but its education effect size was **not verified** in that
  pass — nor were DPP/DSMES — so foot-care/DPP/DSMES numbers must be verified in a dedicated pass
  before they are quoted. Final first-module pick is a clinical call between evidence (exercise/
  balance) and standard-of-care impact (foot care).

## Relationship to the NSI and the dataset

Education is a **behavioral intervention**, not a measurement. It sits *beside* the NSI, never
inside it. Its value to the product's thesis is causal, not compositional: if structured education
improves the ADL/function scores the NSI already tracks, that is a **study outcome** to validate in
the 213-clinic program — exactly the "we move real-world ADL scores" claim, made testable.

## Consequences

- New surface, new capability, new PHI-free progress store; no change to existing measurement code.
- A standing **content-authoring + clinical-review** obligation — modules are a maintained asset,
  not a one-off, and every one needs sign-off before shipping.
- Engagement lift is plausible but **unproven for our app** — treat it as a hypothesis to measure,
  not a claim.

## Deferred (explicitly out of v1)

- **Personalized / adaptive education, coaching, and any individualized recommendation** — these
  lean toward SaMD/CDS and need an FDA-consultant opinion first (gap register).
- **Reimbursement** (DSMES is a billable benefit under specific accreditation) — a business/clinical
  path, not a v1 code decision.
- **Runtime LLM tutoring** on the patient's own data — deferred for the same non-diagnostic reason.

## Honesty invariants

General, non-individualized education only; content is human-reviewed and citation-linked (never
runtime-generated medical claims); progress tracking is PHI-free and never enters the Index;
non-diagnostic, with the standard disclaimer on every module; public/permissively-licensed source
curricula only (any licensed instrument gets legal clearance first).
