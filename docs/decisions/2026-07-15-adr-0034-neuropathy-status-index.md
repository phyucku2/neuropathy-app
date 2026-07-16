# ADR-0034: Neuropathy Status Index (a non-diagnostic, symptom-forward composite)

**Date:** 2026-07-15
**Status:** Accepted
**Supersedes:** **ADR-0033** (the composite *function-only* "30 Day Score"). This ADR replaces
that function-only construct with a three-domain, symptom-forward composite and removes the
contradiction defect ADR-0033 carried (see Decision §6).
**Builds on / relates to:** ADR-0003 (deterministic, explainable trajectory engine), ADR-0006
(research-grade data standard — ALCOA+, append-only, provenance), ADR-0011/0012 (deterministic
core; AI-narration guardrails), ADR-0013 (feature-toggle enforced-flag honesty), ADR-0015 (locked
trajectory contract + AA-contrast locks), ADR-0016 (non-diagnostic posture / `NonDiagnosticNote`),
ADR-0021 (PHI-free observability), ADR-0029/0030 (daily check-in + offline queue).
**Cross-references:** the brainstorm `docs/brainstorm/2026-07-15-clinical-grade-neuropathy-score.md`
(all 17 §6 lenses + biostatistics / health-economics / equity) and the regulatory gap register
`docs/compliance/gap-register/fda.md` (the algorithm is flagged **unvalidated**; this index leans
toward SaMD and is kept **non-diagnostic v1**).

## Context

The trajectory engine fits a per-signal line and judges each signal's direction, but composited
nothing into a single glanceable figure. Clinicians and patients asked for one number. The prior
answer (ADR-0033) was **function-only** — labs excluded, symptoms not yet captured — and it kept the
hero **card color keyed to the multi-signal `direction` vote while the arrow was keyed to the
score's own 30-day delta**, so the two cues could point in opposite directions. Review also found
the score could render **stale data as confidently fresh**, and that direction was conveyed partly
by **color alone** (WCAG 1.4.1). Separately, we had no validated symptom capture at all — the daily
check-in collects only three 0–4 function questions (walking, stairs, balance confidence).

The owner set a clinical-grade direction: a **symptom-forward** composite built from **validated
instruments**, honest about what it is not, and designed so the card can never contradict itself.

> **"Clinical-grade" means built to clinical measurement standards — not clinically validated.** The
> Index is a **non-diagnostic v1 index, pending clinical validation.** No instrument psychometrics are
> invented; uncertain instrument specifics are marked **"confirm against source"** in the brainstorm.

## Decision

Adopt the **Neuropathy Status Index (NSI)** — a single **0–100** figure (higher = better health),
anchored to a real **"as of" date**, presented as **non-diagnostic v1, pending clinical validation.**

1. **Three domains, symptom-forward weights (LOCKED): Symptoms 45% · Function 40% · Physiologic 15%.**
   - **Symptoms (45%)** — pain + numbness/paresthesia from **validated instruments** in the daily
     check-in, **anchored on NTSS-6** (covers the neuropathic pain descriptors *and*
     numbness/paresthesia in one short DPN-oriented instrument; *confirm exact items/scoring against
     source*). Recommended pain read for any added component: **PROMIS Pain Intensity / Interference
     short forms** over **NPSI** for v1 — generic, freely available, standardized T-score metric,
     responsive, and suited to repeated mobile administration; NPSI is held as a later
     phenotyping option. (Reconcile the NTSS-6 ~24h vs PROMIS 7-day recall windows; *confirm*.)
   - **Function (40%)** — balance + gait from **BioMech** (objective; `document_imported` v1,
     ADR-0014) and **ADLs** anchored on **PROMIS Physical Function** and/or **Katz/Lawton/Barthel**;
     ADLs come from the check-in and, **when connected, the EMR**.
   - **Physiologic (15%)** — **HbA1c** glycemic-control bands (ADA-informed, **illustrative pending
     validation**; individualized targets are a physician decision). **B12 / eGFR are future**, not
     in the v1 score.

2. **Normalization & directionality.** Every sub-measure is normalized to a common **0–100,
   higher = better** metric, **inverting pain, numbness/paresthesia, HbA1c** (and postural sway) —
   higher raw = worse for those. Domain scores are the average of their present sub-measures; the
   composite combines domain scores with the 45/40/15 weights. **When a domain is absent, the weights
   are renormalized across the present domains** (never impute an absent domain as 0 — that fabricates
   a false alarm); renormalization changes the number's meaning, which the Confidence indicator
   surfaces. Exact per-measure ranges and HbA1c cut-points are physician-signed config, **illustrative
   pending validation** — clinically defensible weights should ultimately come from validation data,
   not a priori (recorded honestly).

3. **Adherence is Confidence, not health.** Adherence and **BioMech daily completion do NOT enter the
   Index.** They drive only a separate **Confidence / data-completeness indicator (High / Medium / Low)**,
   computed from **domain coverage + data recency** (domain-appropriate freshness windows; the engine's
   `FRESH_WITHIN_DAYS` / `STALE_AFTER_DAYS` primitives). Folding engagement into a health number is
   misleading: it would mask a diligent patient's decline (false reassurance) and penalize an improving
   light user. The Index answers "how is the neuropathy status?"; Confidence answers "how much to trust
   this number?"

4. **Composite delta is the single source of truth for direction.** Direction is the **change in the
   composite itself over ~30 days** (fitted the same deterministic way as the engine, noise threshold
   applied). The **separate multi-signal "direction vote" is removed from this surface**, so the card
   color and the ↑/↓ arrow can never contradict (a real defect found in review). Direction is conveyed
   **in words** (improving / steady / declining) + a glyph, **never by color alone** (WCAG 1.4.1); the
   Index, direction word, delta, `as_of` date, and Confidence level are announced together to assistive
   tech.

5. **Freshness / `as_of` honesty.** The Index carries an explicit **`as_of` date** = the effective date
   of the newest contributing observation (never wall-clock "today"), always shown beside the number. If
   that date is older than the domain-appropriate window, **Confidence degrades and the UI says the data
   is old** — stale data is never rendered as confidently fresh.

6. **Non-diagnostic v1 + validation roadmap.** The Index is **not** a diagnosis, severity stage, or
   risk score. All ADR-0016 non-diagnostic disclaimers co-locate with every surface showing the Index or
   its direction. "Clinical-grade" = built to clinical standards; the **validated** claim is earned only
   after: instrument selection & licensing (*confirm NTSS-6/NPSI permissions; PROMIS/Katz broadly
   available — confirm*), composite psychometrics (reliability, validity, responsiveness/MCID *of the
   composite* in the target population), and a prospective validation study — with the FDA consultant's
   SaMD/CDS opinion gating any clinical/billing-enabling ship (gap register P0/P1).

7. **Engineering commitments.** All scoring is **pure/deterministic**, recomputed on read (no mutable
   rollup stored as source of truth), unit-tested to the ≥85% bar; no new egress; observability stays
   PHI-free (score/confidence as fixed vocabulary, never instrument values, ADR-0021); the Index ships
   behind a **feature toggle** honoring enforced-flag honesty (ADR-0013) until fit to show; new check-in
   fields land as an append-only, reversible migration (ADR-0006).

## Phased build plan

- **Phase 1 — Validated symptom capture (pain + numbness) in the daily check-in.** Real check-in UI
  fields *and* backend schema/ingestion, NTSS-6-anchored (instrument + licensing confirmed against
  source), correct polarity (pain/numbness inverted), research-grade provenance. Additive and
  independently valuable (better trends + a stronger RTM data story); de-risks Phase 2.
- **Phase 2 — Composite + Confidence + card fixes.** The weighted composite (normalization,
  missing-domain renormalization, domain-level 30-day delta), the Confidence indicator, and the card
  fixes: single-source-of-truth delta (retire the multi-signal vote for this surface), direction-in-words
  (WCAG 1.4.1), and `as_of`/freshness so stale data can't read as fresh.

## Consequences

- One honest, glanceable figure replaces four lines of copy, and the **card can no longer contradict
  itself** — color and arrow are driven by the one composite delta; direction is in words.
- The Index is **honest about what it is not**: symptom-forward, instrument-based, renormalized under
  partial data, non-diagnostic, and pending validation. The weights and normalization cut-points are the
  first things a validation plan should scrutinize.
- Symptom capture (Phase 1) has value on its own — richer trends and a stronger RTM data story — before
  the composite exists.
- The composite is itself a **new instrument**: validating its components does not validate its weights,
  scoring, or MCID. The "validated" claim, and any SaMD/reimbursement-enabling build, remain gated on the
  validation study and the FDA consultant's opinion. This ADR asserts **no** regulatory classification and
  **no** validated clinical claim; it processes synthetic data only.

## Addendum — Phase 1 implementation note (symptom capture)

Phase 1 shipped the two symptom items in the daily check-in (backend schema/ingestion/storage +
frontend UI). What was actually built, and the honesty caveats to relay:

- **Items are validated-measure-*aligned*, not the instruments themselves.**
  - **Pain** — a **0–10 Numeric Rating Scale (NRS)**: "Worst pain today (0 = none, 10 = worst
    imaginable)." NRS is a public-domain pain measure; the item is used directly.
  - **Numbness/tingling** — a **0–10 severity item** intended to map onto the **NTSS-6**
    numbness/paresthesia model. **NTSS-6 exact item wording, scoring, and licensing are NOT yet
    confirmed** (this ADR marks the instrument "confirm against source"). Phase 1 therefore uses an
    NTSS-6-*aligned* severity item and **does not reproduce NTSS-6 verbatim**.
  - **No code or UI text claims the capture *is* NTSS-6 or a validated/clinical measure.** Each stored
    observation carries `measure_alignment` (`"NRS-aligned"` / `"NTSS-6-aligned"`) and
    `validated_instrument: false` in its `quality`. **Confirm licensing + exact items before any
    validated/clinical claim, published instrument name, or verbatim wording.**
- **Storage & provenance.** Each answered item stores its own research-grade `Observation`
  (codes `symptom_pain` / `symptom_numbness`, `source=adl`, `origin=patient_reported`), ALCOA+
  provenance (dual UTC timestamps, `recorded_by_role`), corrections-as-new-records via `revises_id`
  (same-day supersession, ADR-0006). No composite/normalization is computed in Phase 1 (Phase 2's job).
- **Polarity is persisted explicitly.** Symptoms are **higher = worse**, the inverse of the function
  answers. Recorded two ways so Phase 2 can invert them correctly: per-observation `quality`
  (`higher_is_worse: true`, `polarity: "lower_is_better"`) **and** the code registry
  (`app/trajectory/directionality.py`).
- **Feature toggle (ADR-0013).** Gated behind a new capability **`ingest_symptoms`**, registered
  **`default=False, enforced=True`** — the first opt-in key (every other shipped key defaults on for
  back-compat). Off by default and honestly enforced: the `/adl` route persists symptom rows **only**
  when the toggle is on for the patient; when off it ignores `pain`/`numbness` entirely regardless of
  what the client sends. The frontend reads the effective toggle and shows the two questions only when
  it is on; when off the check-in behaves exactly as before. Observability stays PHI-free (audit detail
  carries symptom *counts*, never values). **Accepted behavior (enforced-flag honesty):** a symptom
  answer captured offline while the toggle was on is dropped server-side if the capability is disabled
  before the queued check-in syncs — the enforced "off" is the authority, so late-arriving symptoms for a
  now-disabled capability are honestly discarded rather than back-filled, and we deliberately add no
  notification for it.
- **Atomic symptom capture (both-or-neither).** With `ingest_symptoms` on, a check-in that answers ANY
  symptom must answer BOTH pain and numbness; a partial submission is rejected (422). This aligns the
  backend contract with the UI (which already requires both when the section shows) and closes a Phase-2
  data-integrity defect: a same-day re-POST of a single symptom would otherwise supersede only that code
  and leave the other symptom's earlier row current, mixing (e.g.) a morning numbness with an evening pain
  in the day's "current" record that Phase 2 reads per code. When the toggle is off both are ignored as
  before; when on and neither is provided the check-in stays function-only (symptoms optional in aggregate,
  atomic when present).
- **No DB migration.** The new observations reuse existing columns and existing enum values
  (`source_type='adl'`, `data_origin='patient_reported'`); the capability is a lazily-seeded registry
  key. `Base.metadata` is unchanged, so the autogenerate-parity integration test stays green and per
  repo convention (migrations mirror the models) **no Alembic migration is added**.
