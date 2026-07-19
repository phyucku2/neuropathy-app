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

Adopt the **Visit-Ready Summary**: one windowed projection of a patient's record, rendered as
(1) a **patient-held print/PDF** and (2) a **clinician-side view** in the consent-gated panel —
plus the new capture that fills the between-visit gaps. Phased so Phase 1 ships under today's
posture and the interpretive/new-capture/delivery pieces are gated.

**Window (owner decision 2026-07-19):** selectable **30 / 60 / 90 / 120 / 365 days**, default
**60**. At the long windows (120/365) the "what changed" diff loses meaning — everything
changed — so those windows lead with the **trajectory over time** (the existing per-signal
trend) and demote the diff; the short windows lead with the diff. Same data, window-appropriate
emphasis.

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
| **What changed (selected window)** | derived delta | The diff, not the dump (see below). Leads on short windows; demoted under the trajectory view at 120/365. |
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

**Medications & supplements** — new `SourceType.medication`, with a `kind` of
`prescription | otc | supplement` (owner decision 2026-07-19: capture **all three** — both
prescription and OTC/supplements, since supplements drive interactions and B12/neuropathy
effects clinicians rarely hear about). **Three** capture modes, all provenance-tagged:
- **Patient-entered list + change log**: current items, and *change events* (started / stopped
  / dose-changed) with prescriber (free text), date, and optional reason. `origin =
  patient_reported`.
- **FHIR pull** (optional, via the existing SMART connection): `MedicationStatement` /
  `MedicationRequest`, which aggregate meds **across providers**. `origin = ehr_imported`.
- **Camera capture with mandatory patient confirmation (owner decision 2026-07-19):** the
  patient photographs a pill bottle / supplement label; OCR **prepopulates a draft** (name,
  dose, date); the patient **reviews and confirms** before it becomes a final record. This
  reuses the codebase's existing *human-confirm-before-final* pattern exactly:
  - The draft is written as `ObservationStatus.preliminary` ("captured, not yet confirmed —
    e.g. unconfirmed OCR", already in the model) and only the patient's confirm promotes it to
    `final` with a `human_confirmed: True` quality flag — the same contract the lab-OCR path
    already uses. **A misread label never silently enters the record.**
  - **The photo is extract-and-discard:** OCR parses it, the draft is populated, the image is
    **deleted** — the app stores the structured med item, never the picture. (A retained label
    photo is PHI-at-rest with no ongoing purpose.)
  - **OCR route (V1 recommendation): on-device OCR** (e.g. ML Kit via Capacitor) so the photo
    never leaves the phone — avoids sending PHI to a cloud OCR seam. The existing `ocr_provider`
    config seam remains for a **BAA-covered** cloud OCR alternative; cloud OCR is gated on that
    BAA exactly like the AI narrator (ADR-0011/0020). Either way, confirmation and
    extract-and-discard are unconditional.
- The handout then surfaces **"medications/supplements recorded since last visit that may not
  be in your chart"** — the different-provider safety win (polypharmacy / interaction the
  treating clinician can catch). The app **lists and logs; it never adjusts, reconciles, checks
  interactions, or recommends** an item (hard non-diagnostic line — interaction-checking would
  be a distinct device-status question and is explicitly out of scope).

**Notes & events** — lightweight patient capture of the things clinicians never hear:
- **Structured events** (a small closed vocabulary): fall, ER/urgent-care visit, new provider
  seen, hospitalization, new OTC/supplement. Each with a date. `origin = patient_reported`.
- **Free-text note** (optional, short). It is **PHI** → same PHI rules as everything else:
  audit-logged (counts/refs, never values), **not fed to AI narration by default** (only under
  a BAA, and even then never used to generate clinical content), and included on the handout
  verbatim under a clear "patient's own words" label.
- **Clinician read-acknowledgment (owner decision 2026-07-19).** A posted note carries its
  day/time and shows as **"unreviewed"** on the clinician panel; it persists until **any**
  clinician on the patient's care team marks it reviewed (team-wide, so one person's absence
  can't build a stale queue), and the acknowledgment is **audit-logged** (who, when) — the
  accountability that stops notes from being missed.
- **The acknowledgment queue creates a duty-to-review expectation, so this is designed
  defensively (safety + liability):**
  - **Expectation copy at the point of writing (non-negotiable):** "Notes are reviewed by your
    clinician when they can — **this is not monitored in real time.** If it's urgent, call your
    clinic; if it's an emergency, call 911." The unread state must never read as "sent to my
    doctor now."
  - **No emergency detection or triage.** The app does **not** scan note text for red-flag
    phrases and prioritize/route it — that is an interpretive/device function and a promise the
    channel cannot keep. The note channel is explicitly non-urgent, stated in the copy.
  - The unread→read transition is a **workflow/accountability** state, not a clinical judgment;
    it asserts nothing about the note's content.

All of the above require: new model fields/enums, a **files-only Alembic migration** matching
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

## Resolved by owner (2026-07-19)

- **Window** — selectable 30 / 60 / 90 / 120 / 365, default 60 (§Decision).
- **Medication capture** — build **all three** modes (patient-entered, FHIR pull, camera +
  mandatory confirm) and include **supplements**; patient-entered + camera work with no EMR
  registration, the FHIR pull layers in once registered.
- **Notes** — add **clinician read-acknowledgment** (team-wide, audited, with non-real-time
  expectation copy and no emergency triage).

## Open questions (still for the owner / reviewers)

1. **Notes to AI** — keep free-text notes strictly out of the AI path even under a BAA (safest,
   the spec default), or allow rephrasing later?
2. **"Questions to ask"** — ship the data-completeness prompts in Phase 1 and hold the
   change-pointed questions for the D2 opinion, or hold the whole questions block until D2?
3. **OCR route** — confirm on-device OCR for V1 (photo never leaves the phone), with cloud OCR
   only as a later BAA-gated option?
4. **Note SLA** — do we surface any "unread for N days" escalation to the clinic (an ops nudge,
   not a clinical one), or leave the queue un-timed to avoid implying a monitored channel?
