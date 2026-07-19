# ADR-0045 — Visit-Ready Summary (the clinician handout) + between-visit capture gaps (spec)

- **Status:** Proposed (spec — not built). Phase 1 is buildable now under the current
  non-diagnostic posture; Phases 2–3 add new capture/delivery and carry the gates below.
- **Date:** 2026-07-19
- **Builds on:** ADR-0031 (patient data export — the assembly path this reuses), ADR-0034
  (NSI), ADR-0016/0041 (non-diagnostic posture / FDA device-status framework), ADR-0044
  (clinician feedback loop — the delivery-side sibling), ADR-0012/0013/0020 (clinician
  surface + patient-held consent), ADR-0006 (research-grade provenance), ADR-0008/0009/0028
  (SMART-on-FHIR pull), ADR-0039 (accessibility 60+), ADR-0042 (food logging V2).
- **Evidence:** `docs/product/market-position-and-gaps.md` (the outbound clinician loop is a
  table-stakes gap; the clinician is the distribution channel).

> **This is NOT a diagnostic tool and the Summary makes no clinical claim.** The handout
> **re-presents the patient's own recorded data** (patient-reported, imported, or derived),
> each datum labeled with its source and date, so a clinician can **independently review the
> basis**. It does not diagnose, interpret, recommend, or prioritize care. The "questions to
> ask" are **change-surfacing prompts about the patient's own data**, never advice. The
> product is not FDA-cleared and processes synthetic data only.

## Context

The clinician is both the buyer and the sales force: a tool spreads when it makes the
clinician's visit easier and makes them look prepared, at **zero added work**. The single
highest-leverage artifact is a **Visit-Ready Summary** — a windowed, human-readable snapshot
the patient brings (or the clinician opens) at the appointment.

Its real value is not "more data." It is **closing the information gap**: the treating
clinician normally never sees (a) daily functional status and symptom trend between visits,
(b) **medications changed by a *different* provider** (a specialist or urgent-care visit the
PCP learns about months later, if ever), (c) the patient's own between-visit events — a fall,
an ER trip, a new supplement — and (d) labs/data that live in another system. Care
fragmentation is the gap; the app is the one place that aggregates all of it for the person
in the room with the patient.

Two of those four (meds, notes/events) are **not captured today**. So this ADR specs both the
**rendering** (reuse of the ADR-0031 assembly) and the **new capture** that gives the handout
something no other artifact in the visit has.

## Decision

Adopt the **Visit-Ready Summary**: one windowed (default **60-day**, configurable) projection
of a patient's record, rendered as (1) a **patient-held print/PDF** and (2) a **clinician-side
view** in the consent-gated panel — plus the new capture that fills the between-visit gaps.
Phased so Phase 1 ships under today's posture and the interpretive/new-capture/delivery pieces
are gated.

### Phase 1 — Assemble + render from existing streams (buildable now)

**Assembly (reuse, don't rebuild).** Add a windowed, curated projection over the **same read
paths** `PatientDataExportService` already uses (ADR-0031) — never hand-rolled SQL. Input: a
patient id + a window (default 60 days). Output: a typed `VisitSummary` envelope. Because it
rides the export assembly, it inherits the **PHI-safe, secrets-absent-by-construction**
posture and the "current analyzable record" semantics (errored/superseded rows excluded).

**Contents (each datum carries `source` + `origin` label + date — trust *and* the
non-diagnostic guardrail):**

| Section | Source (today) | Notes |
|---|---|---|
| **Status at a glance** | NSI + trajectory (derived) | The 0–100 index + direction/confidence, non-diagnostic note co-located. Leads the page. |
| **What changed (last 60d)** | derived delta | The diff, not the dump (see below). |
| **Symptoms trend** | ADL symptoms (pain 0–10 NRS, numbness NTSS-6-aligned) | Sparkline + start→now. |
| **Function / daily living** | ADL (walking, stairs, balance-confidence) | The data a clinician almost never gets between visits. |
| **Balance & gait** | BioMech (`document_imported`) | Latest vs. prior, per the real catalog. |
| **Labs** | labs (patient-upload or EMR-pulled) | Most recent per analyte + prior, unit-safe (no cross-unit deltas — ADR-0015). |
| **Activity / glucose** | wearable / CGM | Summary stats only. |
| **Medications** | *Phase 2* | Placeholder row rendered "not yet tracked" so the layout is stable. |
| **Notes & events** | *Phase 2* | Same. |
| **Nutrition** | *Phase 3 / ADR-0042* | Same. |
| **Questions to ask** | derived, template-driven | Change-surfacing prompts (see below). |

**"What changed" (deterministic).** Compute the window's diff against the prior window: new
labs, symptom-trend direction (reuse the trajectory engine), adherence/data gaps, latest
BioMech vs. prior. Pure re-presentation of the patient's own deltas — non-diagnostic.

**"Questions to ask" (deterministic, template-driven, change-surfacing — the FDA-sensitive
edge).** Generated from the deltas as **prompts about the patient's own data**, never advice:
- *"Numbness rose from 3→6 over 60 days — ask the patient about it."*
- *"No check-ins in the last 18 days — confirm how they've been doing."*
- *"HbA1c changed since the last recorded value — review in context."*

The deterministic templates are the source of truth. The AI narrator, if a BAA is on, may only
warmth-rephrase them (ADR-0011) — it never generates a new question, number, dose, or
assessment. **Guardrail:** a prompt only ever points at *what changed* and asks the clinician
to look; it never suggests a diagnosis, a treatment, or a priority.

**Rendering.** (1) Patient print/PDF: accessible for 60+ (ADR-0039 — large type, plain
language, AA contrast, print-optimized, one to two pages). (2) Clinician-side view in
`PatientDetailPage`, consent-gated, with a "print/export" affordance. Same `VisitSummary`
data behind both.

### Phase 2 — Capture the between-visit gaps (new models; the differentiator)

**Medications** — new `SourceType.medication`. Two capture modes, both provenance-tagged:
- **Patient-entered med list + change log**: current meds, and *change events* (started /
  stopped / dose-changed) with prescriber (free text), date, and optional reason. `origin =
  patient_reported`.
- **FHIR pull** (optional, via the existing SMART connection): `MedicationStatement` /
  `MedicationRequest`, which aggregate meds **across providers**. `origin = ehr_imported`.
- The handout then surfaces **"medications recorded since last visit that may not be in your
  chart"** — the different-provider safety win (polypharmacy / interaction the treating
  clinician can catch). The app **lists and logs; it never adjusts, reconciles, or
  recommends** a medication (hard non-diagnostic line).

**Notes & events** — lightweight patient capture of the things clinicians never hear:
- **Structured events** (a small closed vocabulary): fall, ER/urgent-care visit, new provider
  seen, hospitalization, new OTC/supplement. Each with a date. `origin = patient_reported`.
- **Free-text note** (optional, short). It is **PHI** → same PHI rules as everything else:
  audit-logged (counts/refs, never values), **not fed to AI narration by default** (only under
  a BAA, and even then never used to generate clinical content), and included on the handout
  verbatim under a clear "patient's own words" label.

Both require: new model fields/enums, a **files-only Alembic migration** matching
`Base.metadata` (the parity test), capture UI, and import-idempotency on the same
`add_if_absent` invariant as every other ingest path (ADR-0045 follows the sweep-#3 rule).

### Phase 3 — Delivery + reimbursement (gated)

- **Morning-of-visit delivery**: push the clinician-side Summary ahead of the appointment
  (works even when the patient forgets the printout). Ties to ADR-0044 Phase A.
- **EHR write-back**: land the Summary (or its PRO components) in the clinician's own workflow
  as FHIR `Observation` / `DocumentReference` — ADR-0044 Phase B, deferred (per-vendor write
  scopes + a dedicated design ADR).
- **Reimbursement linkage**: the Summary's structured evidence (days-with-data, etc.) feeds
  the RTM evidence packet — `reimbursement-signoff-packet.md`. Gated on the FDA D2 finding +
  a certified-coder sign-off; nothing billing-enabling ships ahead of it (ADR-0041 §3).

## Privacy / PHI

- The Summary **is PHI by design** — that is the point. The **patient owns it**; clinician
  access stays behind the patient-held `share_with_clinic` consent, enforced by the single
  server-side access predicate + non-enumerating 404 (ADR-0012/0020).
- Reuses ADR-0031's secrets-absent-by-construction assembly; **no token/hash field exists to
  leak**, proven by the same payload-scan tests.
- Generation and clinician access are **audit-logged** (actor, action, patient ref, counts —
  never values; CLAUDE.md §5).
- **Disclosure honesty:** once printed, the paper artifact leaves the app's control — say so at
  the point of print (a patient-choice disclosure), and label the sheet "current record, not a
  complete medical record" (mirrors ADR-0031's current-not-complete wording).

## Regulatory gates

- **ADR-0041 (device-status).** Phase 1's "what changed" is safe re-presentation. The
  **"questions to ask"** layer edges toward decision support — route it past the D2 consultant
  exactly as ADR-0044 Phase A does (data-completeness prompts are clearly safe; change-pointed
  questions get the opinion). The medication **list/log** is non-interpretive; any future
  medication *reconciliation* would be a new device-status question and is explicitly out of
  scope.
- **BAA** — required before AI rephrasing of any Summary text touches real PHI (ADR-0011).
- **EMR registration** — required for the FHIR medication pull (Phase 2b).
- **Coder + D2** — required for the reimbursement linkage (Phase 3).

## Consequences

- **A concrete, high-visibility clinician win** that is mostly *assembly of data we already
  have* (Phase 1), so the flagship ships fast and non-diagnostically.
- **The differentiator is the capture** (Phase 2): meds-across-providers and between-visit
  events are data no other artifact in the visit has — the real "closes the gap" story, and
  the strongest reason a clinician recommends the app.
- **No posture change today**: Phase 1 re-presents patient-owned data behind existing consent;
  the interpretive/new-capture/delivery pieces are gated, not assumed.
- **Nutrition stays a placeholder row** until ADR-0042 lands, so the layout is forward-stable.

## Alternatives considered

- **Dump the full record to the clinician.** Rejected — clinicians triage by exception; a data
  dump is noise and actively worse than a focused diff. The Summary leads with *what changed*.
- **Let the AI write the summary free-form.** Rejected — an LLM-authored clinical summary is an
  interpretive/SaMD risk and a hallucination surface. The deterministic projection + templated
  questions are the source of truth; AI may only warmth-rephrase under a BAA (ADR-0011).
- **Build meds/notes capture before the render.** Rejected as sequencing — Phase 1 delivers a
  useful handout from existing streams immediately; Phase 2 capture deepens it without blocking
  the flagship.

## Open questions (for the owner / reviewers)

1. **Window default** — 60 days as specced, or clinician-configurable per patient (30/60/90)?
2. **Medication capture priority** — patient-entered first (works with no EMR registration), or
   wait for the FHIR pull (richer, cross-provider, but gated on registration)?
3. **Notes to AI** — keep free-text notes strictly out of the AI path even under a BAA (safest),
   or allow rephrasing later? (Spec defaults to *out*.)
4. **"Questions to ask"** — ship the data-completeness prompts in Phase 1 and hold the
   change-pointed questions for the D2 opinion, or hold the whole questions block until D2?
