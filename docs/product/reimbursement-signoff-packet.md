# Reimbursement Sign-off Packet — Professional Review of the Wave 4 RTM Build

**Date:** 2026-07-14
**Status:** Review packet — **awaiting professional sign-off** (this document *is* the
sign-off vehicle gating Wave 4; see [`../roadmap-status.md`](../roadmap-status.md))
**Audience:** (1) a certified professional coder (CPC), (2) compliance/legal counsel, and
(3) — for §4 only — an FDA regulatory consultant.
**Companions:** [`reimbursement-analysis.md`](reimbursement-analysis.md) (pathway analysis),
[`reimbursement-operations.md`](reimbursement-operations.md) (operational playbook),
[`reimbursed-apps-comparison.md`](reimbursed-apps-comparison.md) (market comparison of
products already billing RTM/RPM — cited below where its findings inform risk).

---

> ## ⚠️ READ THIS FIRST — SCOPE & CAVEAT
>
> This packet is **decision-support material for professional reviewers. It is NOT billing
> advice, NOT coding advice, and NOT legal advice**, and nothing in it authorizes anyone to
> bill Medicare, Medicaid, or any payer. Every code-mapping statement in §3 is phrased as an
> **assertion for reviewer validation**, never as a conclusion. CPT® is a registered
> trademark of the AMA; descriptors are paraphrased. Codes, thresholds, supervision rules,
> and rates change at least annually and vary by MAC and state Medicaid program — reviewers
> should validate against the current primary sources cited here and in the companion docs
> (all URLs accessed 2026-07-14).

---

## 1. Purpose and the exact decisions requested

The product roadmap ([`../roadmap-status.md`](../roadmap-status.md), Wave 4) gates all
reimbursement-enabling feature work on professional sign-off. This packet asks the
reviewers for **three decisions** — each has a signature line in §6:

| # | Decision requested | Primary reviewer | What "approve" unlocks |
|---|---|---|---|
| **D1** | **Approve or reject the RTM-first feature build** — the prioritized backlog in [`reimbursement-analysis.md`](reimbursement-analysis.md) §7 (parameterized days-with-data counter, interactive-time ledger, episode/setup event, billing-consent scope, billing-evidence export, provenance strengthening) | Certified professional coder **+** compliance counsel | Wave 4 build starts. Rejection or conditions kill or reshape the wave. |
| **D2** | **Resolve the FDA device-status question** (§4): primarily, is our own software a device (SaMD) under FD&C Act §201(h) — and if so, what obligations follow; secondarily, does the BioMech data source meet the device definition (BioMech's determination; our data-provenance dependency — see the §2.4 scope boundary) | FDA regulatory consultant (with owner) | Determines whether RTM device-supply codes are even *available* to a billing clinic using this app, and whether our software needs a regulatory strategy before Wave 4 ships. |
| **D3** | **Approve the billing-consent model** — a distinct billing-consent scope, separate from care/research consent, captured in-app with modality/version/timestamp (wording to be supplied by counsel) | Compliance counsel | The billing-consent capture feature (backlog item 4) is built with approved scope + wording. |

**What we are NOT asking:** no reviewer is asked to approve a claim, a code on a claim, a
payer submission, or an FDA submission. The app's posture is **enabler-not-biller**
([`reimbursement-operations.md`](reimbursement-operations.md) §0): a servicing clinic
bills; the app only captures facts and exports evidence.

## 2. Product facts a reviewer needs (with pointers into the repo)

Stated from the codebase's decision records — reviewers can verify each pointer.

### 2.1 Data streams and provenance

| Stream | Provenance origin today | Pointer |
|---|---|---|
| BioMech balance & gait metrics (balance score, sway velocity/area, gait speed, cadence, step length, step-time symmetry) | `document_imported` — V1 parses BioMech's **PDF reports** (text layer only, closed metric registry, never fabricates values); `device_measured` is **reserved for a V2 API/SDK path that is deferred** | ADR-0014 (`../decisions/2026-07-13-adr-0014-biomech-pdf-ingest.md`); deferral: roadmap "Deferred" |
| ADL daily check-ins (patient-reported functional status/symptoms, supersede-by-revision) | `patient_reported`, contemporaneous, attributable | ADR-0006 (`../decisions/2026-07-11-adr-0006-research-grade-data-collection.md`) |
| Labs (LOINC/UCUM-coded, FHIR R4-aligned; patient-imported or SMART-on-FHIR EMR pull) | EMR-pulled / imported **point-in-time results** — not a patient-held auto-transmitting device | ADR-0007/0008/0009 |
| Trajectory engine output (direction/confidence/signals) | `derived`, deterministic and explainable; **non-diagnostic** | ADR-0003, ADR-0016 |

All observations are **research-grade**: ALCOA+, immutable/append-only (corrections via
superseding records, never overwrite), dual timestamps (`effective_at` + `recorded_at`),
full provenance (origin, source system, method, version, recorder role), 21 CFR Part 11
alignment — ADR-0006. **Reviewer relevance:** every "day with data" a future adherence
counter reports is backed by an attributable, immutable capture event.

### 2.2 Capability status — what exists vs. what Wave 4 would build

| Capability | Status today | Wave 4 item |
|---|---|---|
| Provenance-complete observation store (the raw material for days-with-data evidence) | **Built, merged** | — |
| Parameterized days-with-data adherence counter (2–15 / 16–30-day tiers per 30-day period) | **Not built** | analysis §7 item 1 |
| Interactive treatment-management **time ledger** (minutes per clinician per patient per calendar month + ≥1 live-communication event) | **Not built — no timer or time capture of any kind exists in the app today** | analysis §7 item 2 |
| Episode-of-care + setup/onboarding event (98975-type evidence) | **Not built** | analysis §7 item 3 |
| Billing-consent scope | **Not built** (consent scopes exist and are separable — see 2.3) | analysis §7 item 4 |
| PHI-safe billing-evidence export | **Not built** | analysis §7 item 5 |
| Audit trail: PHI reads/writes audit-logged (actor, action, patient reference, counts — never values); immutable record-change history | **Built, merged** | — (ADR-0012, ADR-0021) |

### 2.3 Consent model

Consent scopes are already **separated by design**: care use vs. research use are distinct
(ADR-0006), and clinician data access is gated by a **patient-held** consent
(`share_with_clinic`) that the patient always controls even in the clinician-managed
deployment — enforced server-side through a single access predicate with a
non-enumerating 404 posture (ADR-0012, ADR-0020). **Billing consent does not exist yet**;
D3 asks counsel to approve adding it as a further distinct scope recording modality
(verbal/written), version, timestamp, and — where CCM/PCM ever applies — the required
disclosures ([`reimbursement-operations.md`](reimbursement-operations.md) §HOW-3).

### 2.4 The enabler-not-biller posture — and its scope boundary

The app does not enroll with Medicare, does not submit claims, and never asserts a final
code, FDA status, or medical necessity. It captures billable *facts* (days, minutes,
communications, consent, provenance) and exports a read-only, audited, PHI-safe evidence
packet labeled "candidate — not a claim" ([`reimbursement-operations.md`](reimbursement-operations.md)
§0, §HOW-5). Business roles: the repository owner owns the IP; **BioMech Health is a
licensee** (ADR-0001); the billing entity would be a servicing clinic, not us and not
BioMech-as-manufacturer.

**Recorded owner decision (2026-07-14): "BioMech is billed separately as for now."**
BioMech's device/assessment service has its **own, separate billing arrangement that is
outside this app's reimbursement-enablement scope**. What the app enables — and what
reviewers are asked to evaluate — is a servicing clinic's potential claims around the
**app-captured streams**: ADL self-report, the **imported BioMech report data** (as data
in our store), and EMR labs. BioMech's own billing for its assessments/device is **not**
part of what our app enables or evidences. *As of 2026-07-14; revisit this boundary if
the BioMech relationship changes.*

### 2.5 Non-diagnostic posture (load-bearing for §4)

The product ingests, graphs, and analyzes; it does **not** measure, diagnose, or recommend
treatment (ADR-0003). The clinician surface presents computed trends deterministically and
is explicitly non-diagnostic (ADR-0016). Marketing and UI copy hold this line. This
posture is a **factual input to the SaMD determination** in §4 — it constrains intended
use, and changing it would change the regulatory analysis.

## 3. The claims mapping to review

Each row is an **ASSERTION for reviewer validation** — drawn from
[`reimbursement-analysis.md`](reimbursement-analysis.md) (§2–§4, with sources there),
restated here so the CPC can mark each one validated / corrected / rejected. None is a
conclusion; the app will not surface any code family in an export until the corresponding
assertion is professionally validated.

| # | ASSERTION for reviewer validation | Basis (see analysis doc for sources) |
|---|---|---|
| **A1** | BioMech balance/gait metrics constitute **musculoskeletal-system data** eligible for the RTM device-supply family — 98977 (16–30 days of data per 30, as revised CY2026) and 98985 (2–15 days, new CY2026) — *provided* the FDA device gate (§4) is resolved affirmatively | analysis §2, §2.1 |
| **A2** | ADL daily check-ins qualify as **self-reported therapeutic-response data** acceptable for RTM (RTM permits patient self-report, unlike RPM) | analysis §2 |
| **A3** | (Negative assertion) EMR-pulled point-in-time labs do **not** satisfy RPM 99453/99454's device-collected, auto-transmitted physiologic-data requirement, so **RPM is not a viable pathway as built** | analysis §3 |
| **A4** | The planned evidence-packet fields — tiered days-with-data with per-day attributable events, itemized minutes with actor role, ≥1 live-communication timestamp, setup/episode event, order-exists flag, consent state — are the **correct and sufficient documentation basis** for a clinic's coder to evaluate 98975 / 98977 / 98985 / 98979 / 98980 / 98981 candidates | operations §WHAT, §HOW-5 |
| **A5** | The adherence thresholds must be modeled as **two tiers (2–15 and 16–30 days per 30-day window)** per the CY2026 PFS final rule, not a single ≥16-day rule | analysis §2 (CY2026 changes) |
| **A6** | RTM management (98980/98981) must never be billable alongside RPM management (99457/99458) for the same patient in the same period, and only one practitioner bills per patient per 30-day period — so the export must carry **mutual-exclusivity flags** | analysis §2, operations §WHEN |
| **A7** | The service can be **ordered by a physician/QHP including a physical therapist**, furnished under **general supervision**, with clinical-staff time billable incident-to — the assumptions the time-ledger's actor-role tagging is designed around | operations §WHO |
| **A8** | CCM/PCM (99490/99424 families) is correctly deprioritized to a **second wave** (needs a care-plan artifact we don't have; per-practitioner exclusivity rules apply) | analysis §4 |

**Reviewer output requested per row:** validated as stated / validated with corrections
(state them) / rejected (state why). A rejection of A1 *or* an adverse §4 determination
kills the RTM-first premise (D1).

## 4. THE FDA QUESTION (for the regulatory consultant)

**Why it decides everything:** CMS requires that RTM (and RPM) data come from a **"medical
device as defined by the FDA"** — the FD&C Act **§201(h)** definition
([CY2022 PFS final rule, 86 FR 65115](https://www.federalregister.gov/documents/2021/11/19/2021-23972/medicare-program-cy-2022-payment-policies-under-the-physician-fee-schedule-and-other-changes-to-part);
[CMS Remote Patient Monitoring coverage page](https://www.cms.gov/medicare/coverage/telehealth/remote-patient-monitoring)).
Neither cited source states who adjudicates a product's device status; in practice the
determination is made against FDA's definition by the manufacturer/biller and their
advisors — WHICH IS EXACTLY WHY this packet asks the regulatory consultant for a written
determination rather than treating the question as settled (inference, not a cited CMS
statement — reviewer to confirm).
FDA's own framing of the definition and of when software is a device:
[How to Determine if Your Product is a Medical Device](https://www.fda.gov/medical-devices/classify-your-medical-device/how-determine-if-your-product-medical-device)
and [Software as a Medical Device (SaMD)](https://www.fda.gov/medical-devices/digital-health-center-excellence/software-medical-device-samd).
The market comparison ([`reimbursed-apps-comparison.md`](reimbursed-apps-comparison.md))
found that among products **verifiably billing RTM today**, those with objective data
streams hold at least a 510(k)-exempt FDA registration/listing for their own software
(Exer AI, OneStep), one software-only enabler shows no FDA footprint and leaves the
§201(h) burden with the billing provider (Limber Health), and FDA's 2025 Warning Letter
to Exer Labs shows the enforcement risk of overstepping a listing's exemption — this
question is not academic, and under the §2.4 scope boundary our nearest structural
comparables are exactly those **software-led** products.

**Our software's FDA status is UNDETERMINED. That is the open question — this packet
frames it; it does not answer it.** Two determinations are needed, but the owner decision
recorded in §2.4 ("BioMech is billed separately as for now") **re-weights them**: because
BioMech's device/assessment service bills under its own separate arrangement and is not
what our app enables, the clinic scenario this packet covers is **not** one where RTM
device-supply codes are billed against the BioMech hardware *through us*. That makes
**4.b — whether OUR software qualifies under §201(h) / as SaMD — the primary live
determination for our scope**, while 4.a (the BioMech hardware) becomes **BioMech's own
problem as manufacturer**, relevant to us mainly as a **data-provenance dependency** of
the imported report stream. Both sub-questions remain below; the consultant should still
answer both, weighted accordingly. (Revisit the weighting if the BioMech relationship
changes.)

### 4.a The BioMech data source (secondary — manufacturer's problem; our data-provenance dependency)

Whether BioMech's wearable-IMU balance/gait system (hardware + their software) meets
§201(h) is **BioMech Health's determination as manufacturer**, not ours. Under the §2.4
scope boundary it no longer gates our primary build path by itself — but it still matters
wherever a reviewer wants the *imported BioMech report data* to carry device-grade weight
in RTM evidence (assertion A1), so obtain the facts. Factual inputs to obtain from
BioMech:

1. Is the BioMech system **FDA-registered and listed**? (Establishment registration +
   device listing are verifiable; see FDA's
   [Device Registration and Listing](https://www.fda.gov/medical-devices/how-study-and-market-your-device/device-registration-and-listing).)
   Registration/listing is **not** clearance — but §201(h) qualification does not
   necessarily require clearance either; the consultant should state which posture BioMech
   actually holds (cleared / listed Class I-II exempt / unregulated wellness).
2. Any **510(k) number**, device class, and the cleared/listed **intended use** — and
   whether balance/gait monitoring of neuropathy patients falls inside it.
3. Whether the data path we ingest (V1: **PDF report export**, `document_imported`)
   preserves an acceptable evidentiary chain from the device, or whether the deferred V2
   API/SDK (`device_measured`) is a practical precondition for defensible RTM device-supply
   claims (analysis §7 item 6).

### 4.b Our software as a possible SaMD (PRIMARY — our problem)

Under the §2.4 scope boundary this is the determination that decides our Wave 4 scope: if
the clinic's monitoring "device" is anything we enable, it is **our software** (capturing
ADL self-report and holding the imported data), so the live question is whether our app
meets §201(h). The consultant is asked to determine whether **our app** — ADL capture +
ingest/graph + deterministic trajectory analysis, explicitly non-diagnostic (§2.5) — is
(i) not a device, (ii) a device under enforcement discretion, or (iii) a regulated SaMD;
and what follows for RTM eligibility of the **ADL stream specifically** (if ADL
self-report is the "device," the qualifying device can only be our software). Factual
inputs and the governing frameworks:

- **Intended use as documented:** ingest/graph/analyze, improving-vs-not trending,
  no diagnosis, no treatment recommendation (ADR-0003, ADR-0016); AI narration is a
  warmth-rephrasing of a deterministic result, off by default, never in the request path
  (ADR-0011).
- **Governing guidances to apply:**
  [Policy for Device Software Functions and Mobile Medical Applications](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/policy-device-software-functions-and-mobile-medical-applications);
  [Clinical Decision Support Software guidance](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/clinical-decision-support-software)
  (does the clinician-facing trend surface stay non-device CDS given its transparency /
  independent-review design?);
  [General Wellness: Policy for Low Risk Devices](https://www.fda.gov/regulatory-information/search-fda-guidance-documents/general-wellness-policy-low-risk-devices)
  (reissued 2026-01-06 — is our patient-facing posture a wellness function, and does that
  survive our disease-specific, neuropathy-monitoring framing?).
- **The tension the consultant must resolve, stated bluntly:** our safest regulatory
  posture (non-device decision-support/wellness) and the RTM revenue posture (data source
  must be a §201(h) device) **pull in opposite directions for the ADL stream** — and the
  §2.4 owner decision (BioMech billed separately) makes this tension the central question
  rather than a side case, because our software is now the only device-candidate in the
  scenario we enable. If the consultant finds the imported-BioMech-data path can carry the
  device qualification via BioMech's own status (4.a), our software may stay non-device
  and RTM evidence rides on that stream. If ADL-as-device is wanted, our software likely
  needs a deliberate device posture (registration/listing at minimum, possibly clearance)
  with everything that entails (QMS, adverse-event reporting, marketing-claim discipline).
- **Determination requested:** a written opinion selecting the posture per stream
  (BioMech stream / ADL stream), the resulting obligations, and whether Wave 4 should build
  RTM evidence for both streams or the BioMech stream only. This becomes the
  **FDA-status decision ADR** (analysis §7 item 7).

## 5. Open compliance items (known gaps — disclosed, not hidden)

From [`../compliance/baa-inventory.md`](../compliance/baa-inventory.md),
[`../compliance/hipaa-ops-checklist.md`](../compliance/hipaa-ops-checklist.md), and the
roadmap:

1. **No hosting provider selected; no hosting BAA executed** — prerequisite before any real
   PHI (BAA inventory item 3).
2. **Anthropic BAA not executed** — AI narration is gated OFF until the covered entity
   attests a BAA (ADR-0011; BAA inventory item 1). Not needed for Wave 4, but open.
3. **HIPAA validation is not complete** — the checklist maps app-implemented safeguards
   honestly, but all **[CE]** items (risk analysis, training, physical safeguards, BAAs)
   are the covered entity's and are open; the roadmap explicitly notes "HIPAA validation +
   BAAs before real data."
4. **Billing-consent scope not built** (D3 gates its build); no billing consent has ever
   been captured from any patient.
5. **No production deployment exists**; Epic/Cerner production EMR enrollment is Wave 3
   and pending.
6. **Account/data deletion flow not built** (required pre-store; ADR-0026 note) —
   relevant to counsel's retention analysis alongside the operations doc's
   plan-for-10-years retention guidance.
7. **Interactive-time ledger and adherence counter do not exist yet** (§2.2) — no claim
   evidence can be produced today; nothing has been billed and nothing is billable as-is.

## 6. Sign-off sheet

Each reviewer signs for their decision(s) only. "Approve with conditions" must list the
conditions; conditions become Wave 4 gate items.

### D1 — RTM-first feature build (approve / approve with conditions / reject)

| Field | Certified professional coder | Compliance/legal counsel |
|---|---|---|
| Name | ______________________ | ______________________ |
| Credential / bar no. | ______________________ | ______________________ |
| §3 assertions validated (A1–A8, with corrections attached) | ______________________ | n/a |
| Decision | ☐ Approve ☐ Approve w/ conditions ☐ Reject | ☐ Approve ☐ Approve w/ conditions ☐ Reject |
| Conditions (attach) | ______________________ | ______________________ |
| Signature / date | ______________________ | ______________________ |

### D2 — FDA device-status determination (§4)

| Field | Regulatory consultant |
|---|---|
| Name / credential | ______________________ |
| 4.a BioMech source determination (attach written opinion) | ______________________ |
| 4.b Our-software SaMD determination (attach written opinion) | ______________________ |
| RTM evidence build scope | ☐ Both streams ☐ BioMech stream only ☐ Neither (kill) |
| Signature / date | ______________________ |

### D3 — Billing-consent model

| Field | Compliance/legal counsel |
|---|---|
| Name / credential | ______________________ |
| Approved consent scope + wording (attach) | ______________________ |
| Decision | ☐ Approve ☐ Approve w/ conditions ☐ Reject |
| Signature / date | ______________________ |

---

> ## ⚠️ CAVEAT (bottom — same weight as the top)
>
> **Decision-support material only — NOT billing, coding, or legal advice.** Nothing here
> authorizes anyone to bill any payer, and no feature described here ships until the
> sign-offs above exist (roadmap Wave 4 gate). All external claims are cited inline or in
> the companion documents; all URLs accessed 2026-07-14.
