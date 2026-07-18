# ADR-0041 — FDA device-status decision framework (SaMD / §201(h))

- **Status:** Proposed — **framework accepted; the classification itself is deferred to a
  qualified FDA regulatory professional (decision D2).** This ADR does **not** classify the
  software.
- **Date:** 2026-07-18
- **Builds on:** ADR-0003 (SaMD flagged, counsel/regulatory required), ADR-0011/0016/0020
  (non-diagnostic posture, AI guardrails, BAA gate), `docs/compliance/gap-register/fda.md`,
  `docs/product/reimbursement-signoff-packet.md` §4/D2, `docs/product/market-position-and-gaps.md`.

> **This is NOT a regulatory determination, clearance, or claim of FDA compliance.** The
> product is **NOT FDA-cleared, -listed, or -registered.** Whether the software — or its
> "improving/declining" trajectory output — is a §201(h) device / Software as a Medical
> Device is an **open regulatory question that only a qualified FDA regulatory professional
> may answer.** This ADR records the *decision framework and the deferral*, not the answer.

## Context

Every strategic doc converges on the same gate: the FDA device-status question is unresolved,
and it blocks the paths that matter — clinical claims, reimbursement (RPM/RTM require an
FDA-defined device), and any production EMR/marketing posture (`market-position-and-gaps.md`;
`reimbursement-analysis.md`). The posture that *keeps the non-device option open* is already
built and scattered across the codebase and ADRs (deterministic explainable trajectory,
non-diagnostic notes co-located with every direction surface, AI narration guardrailed and
off pending a BAA, BioMech billed separately). What is missing is a **single decision record**
that (a) names the question precisely, (b) enumerates the postures and their consequences,
(c) sets the rules that hold *until* a professional renders the determination, and (d) defines
the triggers that would force a device path — so the deferral is *governed*, not just implicit.

The classification is genuinely not ours (engineering's) to make. This ADR therefore decides
the **framework and the guardrails**, and routes the **determination** to decision D2.

## Decision

**1. Target posture (working hypothesis, pending sign-off): non-device.** We operate and build
as if the software is a **non-device** function — either general-wellness or a non-device
**Clinical Decision Support** function under the Cures §520(o)(1)(E) carve-out — while treating
that as an *unconfirmed hypothesis*, not a conclusion. All engineering continues to preserve
this option (see §3). This is a posture choice, not a legal finding.

**2. The determination is deferred to a qualified FDA regulatory professional (D2).** Before
any **billing-enabling, clinical-claim, or marketing** build ships, we obtain a written
§201(h)/SaMD opinion covering: the trajectory/NSI output against the four §520(o) CDS criteria
(including the patient-facing-audience and device-derived-signal prongs); general-wellness
eligibility given the neuropathy-specific framing and product name; and the
accessory-vs-standalone-SaMD sub-question relative to BioMech. That written opinion becomes the
**accepted** successor to this ADR.

**3. Gating rules that hold until the determination (binding now):**
- **No diagnostic, treatment, predictive, or disease-management claims** anywhere — UI, store
  listings, marketing, or investor materials. Claims stay at *non-diagnostic trend
  visualization*.
- **No reimbursement/billing-enabling build ships** (RTM operational layer, etc.) ahead of the
  determination — it presupposes a device finding (`reimbursement-signoff-packet.md` §4).
- **AI narration stays BAA-gated and off** by default (ADR-0011/0020); it never diagnoses,
  doses, or asserts causation.
- **A marketing-claims review gate** applies to any outward copy (a named reviewer signs off
  that copy does not drift into device claims).
- **BioMech stays billed/regulated separately** (owner decision 2026-07-14); imported BioMech
  data keeps `document_imported` provenance and is **not** given device-grade weight in any
  claim.

**4. Triggers that would force the device path** (any one → re-open as a device program before
shipping the triggering change): attaching a clinical/predictive claim to the NSI or
trajectory; enabling reimbursement that requires a device; marketing that a reasonable reader
would read as diagnosis/treatment; or giving device-derived signals decision-grade weight in a
patient-facing interpretation. Hitting a trigger converts the contingent items in the gap
register (QMS/§820, IEC 62304, ISO 14971, Part 11 e-signatures, GMLP/PCCP, premarket pathway,
registration/listing, postmarket/MDR, §524B cybersecurity, IEC 62366 human factors) from
"deferred" to "required-before-ship."

**5. One controlled intended-use statement of record.** Consolidate the intended-use language
now distributed across ADR-0003/0016 and UI copy into a single version-controlled statement,
reviewed by the consultant + counsel, as the anchor the claims gate checks against (gap
register P1). *(Drafting that statement is a follow-up task under this ADR.)*

## Consequences

- **The deferral is now explicit and governed**, not scattered — a reviewer (or the consultant)
  can read one record and see the posture, the rules, and the triggers.
- **No engineering behavior changes today.** This ADR ratifies the posture already in code and
  binds future claims/features to the gates above. It is safe to keep building non-claim
  product (measurement rigor, accessibility, EMR patient-access plumbing) under it.
- **The one decision that unblocks the most** (per `market-position-and-gaps.md`) is now framed
  for the consultant: engaging them and capturing the written D2 opinion is the single
  highest-leverage next action, and it is an **owner/organizational** action, not an
  engineering one.
- **What this ADR still does not do:** classify the software, establish CDS-carve-out
  eligibility, or assert general-wellness status. Those remain open until the professional
  opinion lands.

## Alternatives considered

- **Make the call in-repo (engineering/AI decides it's non-device).** Rejected — improper and
  unsafe; §201(h)/CDS eligibility is a regulatory-legal conclusion. The repo has correctly
  refused this from ADR-0003 onward; this ADR preserves that refusal.
- **Assume the device path now and stand up QMS/§820/62304/14971 immediately.** Rejected as
  premature — a large program built speculatively before the determination, and possibly
  unnecessary if the non-device posture holds. Kept as a *gated* program (trigger-driven, §4).
- **Leave the posture implicit (status quo).** Rejected — the market/reimbursement analyses show
  the unresolved gate is the top strategic risk; an ungoverned deferral invites accidental
  claim-drift that would forfeit the non-device option. A written framework is the mitigation.
