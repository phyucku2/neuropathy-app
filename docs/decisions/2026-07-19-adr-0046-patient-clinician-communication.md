# ADR-0046 — Patient↔clinician communication + interactive-time ledger (spec)

- **Status:** Proposed (spec — not built). Phase A/B are buildable as a **care + documentation**
  feature under today's posture; the **billing-enabling** use (Phase C) is gated on D1 + D2.
- **Date:** 2026-07-19
- **Builds on:** ADR-0044 (clinician feedback loop — which explicitly deferred messaging as "a
  separate product surface with its own privacy/retention design"; this is that ADR), ADR-0045
  (Visit-Ready Summary — the note read-acknowledgment is the adjacent surface), ADR-0012/0020
  (clinician surface + patient-held consent), ADR-0041 (FDA device-status framework),
  ADR-0006/0021 (research-grade provenance / PHI-free observability), ADR-0027/0031 (retention /
  right-of-access).
- **Reimbursement grounding (assertions for the certified coder to validate — never settled
  fact):** `docs/product/reimbursement-analysis.md` §RTM (98980/98981 require **≥20 min**
  treatment-management/month **and ≥1 live interactive communication**; :75/:119/:245),
  `reimbursement-operations.md` (time-log with date/duration/activity + a live-communication
  event; :154/:176/:300 — missing interactive communication is a top denial reason),
  `reimbursement-signoff-packet.md` (the interactive-time ledger is **named but NOT built**,
  gated on the **D1** coder+counsel and **D2** FDA sign-offs; :70/:36).

> **This is NOT a diagnostic tool, NOT a real-time/urgent channel, and NOT billing advice.**
> Messaging is non-urgent (the copy says so; emergencies → 911). The app captures *facts*
> (messages, minutes, a logged live-communication event); it **never asserts a CPT code, bills,
> or claims medical necessity** — a servicing clinic bills, the app only evidences
> (enabler-not-biller, `reimbursement-operations.md` §0). Reimbursement statements here are for
> a coder to validate. The product is not FDA-cleared and processes synthetic data only.

## Context

ADR-0044 named the outbound clinician loop a table-stakes gap and **deferred messaging**. The
Visit-Ready Summary work (ADR-0045) then surfaced that a patient↔clinician channel is *also* the
missing **reimbursement building block**: RTM treatment-management billing needs a documented
**interactive-time ledger** and a **live interactive communication** each month, and the app has
**no time capture of any kind today** (signoff-packet). So the channel is dual-purpose — a real
care feature *and* the evidence spine for remote-monitoring reimbursement.

The precise, coder-checkable nuance: **asynchronous messaging does not by itself satisfy the
"≥1 live interactive communication"** requirement — that needs a synchronous call/video. So the
ledger must record a **separate, explicit live-communication event**, not infer it from message
traffic. And the whole billing use is gated (D1 coder+counsel, D2 FDA device). We therefore spec
the **care surface + neutral documentation** as buildable, and gate only the **billing-enabling
export**.

## Decision

Adopt a **consent-gated, non-urgent, audited patient↔clinician communication surface** plus an
**interactive-time ledger**, phased so care value ships without presupposing a billing finding.

### Phase A — Two-way async messaging (care feature, buildable now)

- **Threaded async messages** between a patient and their care-team clinicians, behind the
  existing patient-held `share_with_clinic` consent + single server-side access predicate
  (ADR-0012/0020). Message bodies are **PHI**: audited as reads/writes (counts/refs, never
  values — CLAUDE.md §5), never in structured/observability logs (ADR-0021), retained under the
  ADR-0027/0031 retention + right-of-access rules.
- **Non-urgent by construction (non-negotiable, mirrors ADR-0045 notes):** point-of-send copy —
  *"Messages are reviewed by your clinician when they can — not monitored in real time. Urgent?
  Call your clinic. Emergency? Call 911."* **No red-flag text scanning / triage** (that is an
  interpretive/device function and a promise the channel can't keep).
- **Read state + acknowledgment** reuse the ADR-0045 pattern (team-wide, audited who/when).
- **Non-diagnostic:** the app transports and stores messages; it does not summarize, interpret,
  or auto-respond. (Any AI drafting/summarizing of clinical messages is out of scope and would
  be a separate device-status question.)

### Phase B — Interactive-time ledger (documentation, care-neutral, buildable now)

Per **clinician × patient × calendar month** (the units the codes count in):
- **Accrued minutes** of treatment-management work, each entry with **date, duration, activity
  description, and actor role** (physician vs clinical staff — whose minutes, because some codes
  require the professional's own time; operations.md:120).
- **A logged "live interactive communication" event** — a call/video conducted **outside** the
  app that the clinician records with a timestamp (the required synchronous contact the async
  thread does not provide).
- **Integrity:** injected clock (no wall-clock — `docs/lessons.md`), **append-only/immutable**
  entries (ALCOA+, ADR-0006), fully audited. Time must be **genuine clinician work, not app
  time** (a stated guard; the ledger records what the clinician attests).
- This is **care documentation** on its own; it becomes billing evidence only through Phase C.

### Phase C — Billing-enabling RTM evidence export (GATED)

- Package days-with-data + the ledger minutes + the live-communication event into the
  PHI-safe "candidate — not a claim" evidence packet (`reimbursement-operations.md` §HOW-5).
- **Gated on D1 (certified coder + compliance counsel) and D2 (FDA device finding)** — RTM data
  must come from a §201(h) device, and the code mappings need coder validation (ADR-0041 §3;
  signoff-packet §4/§6). Nothing billing-enabling ships before those sign-offs. **Guards the
  coder must confirm:** no double-counting RTM vs CCM/PCM time; one practitioner per patient per
  30-day period; async time counts toward minutes but only a **live** contact satisfies the
  interactive-communication requirement.

## Privacy / PHI

Consent-gated (patient-held), PHI-audited (counts/refs only), retention + right-of-access under
ADR-0027/0031, PHI kept out of all structured/proxy logs (ADR-0021). Message content and the
ledger's activity descriptions are PHI; the live-communication event stores a **timestamp +
attestation**, never a call recording (recording is explicitly out of scope).

## Consequences

- **Care value ships without a billing finding** (Phases A/B): a real two-way channel + honest
  documentation, both non-diagnostic and non-urgent.
- **The reimbursement spine finally exists** (the ledger) — but its *use* stays behind the D1/D2
  gates, so we capture evidence without ever asserting a claim.
- **Adoption + engagement lever:** clinicians engaging via the channel is exactly the driver the
  market analysis flagged for 60+ retention (ADR-0044 context).

## Alternatives considered

- **Built-in synchronous audio/video (in-app telehealth).** Deferred — it would satisfy the live
  interactive-communication requirement *in-app* and auto-capture it, but it is a large build
  (real-time media infra, a vendor, recording/retention + added compliance) disproportionate to
  V1. Phase B's logged-external-call event captures the same evidence at a fraction of the cost;
  revisit in-app video if the reimbursement path is validated and demand is proven.
- **Infer the live contact from message activity.** Rejected — async ≠ synchronous; inferring it
  would manufacture unsupported billing evidence (the exact denial pattern in operations.md:300).
- **Fold messaging into ADR-0045.** Rejected — it is a distinct surface with its own
  privacy/retention/reimbursement design (ADR-0044 already said so).
- **Ship messaging with no reimbursement coupling at all.** Viable and simplest, but leaves the
  named-but-unbuilt time ledger unbuilt; Phase B adds it as care-neutral documentation without
  presupposing the billing finding, so the coupling is captured honestly rather than dropped.

## Open questions (for the owner / reviewers)

1. **V1 comms shape** — async messaging + logged live-call event (this spec's default), full
   in-app audio/video, or messaging as a care-only feature with no ledger? *(Recommended
   default assumed; a one-line change flips it.)*
2. **Retention** — message + ledger retention period, aligned to the operations doc's
   plan-for-10-years billing-record guidance vs. the patient's right-to-erase (ADR-0027)?
3. **Actor-role source** — infer physician-vs-clinical-staff from the authenticated clinician's
   role, or capture it per ledger entry?
4. **Who may message** — any care-team clinician ↔ patient, or a named responsible clinician
   only?
