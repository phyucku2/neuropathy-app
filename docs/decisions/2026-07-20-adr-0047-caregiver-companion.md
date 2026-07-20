# ADR-0047 — Caregiver Companion (name TBD) — patient-invited loved-one app (spec)

- **Status:** Proposed (spec — not built). The caregiver surface is **buildable under today's
  posture**: it is the patient authorizing disclosure of their *own* health information to their
  *own* loved one (the patient's right), reusing the existing patient-held consent primitive. The
  **caregiver subscription is direct-pay consumer revenue — explicitly NOT a billed/reimbursed
  service** (see §"Two revenue lines"). No new device posture is implied.
- **Date:** 2026-07-20
- **Name:** **TBD.** A preliminary knockout screen (2026-07-20) found the first-choice "Kinly"
  **not viable** — a live Class 9 software registration (Kinly Holding B.V./Yorktel-Kinly), an
  existing same-name family-organizer app, a "Kinly Care" caregiving user, and a documented
  app-store trademark takedown of a different "Kinly" app. Dictionary-word backups (Alongside,
  Anchor, Near, Hearth) were also CAUTION/blocked in health/wellness. **Direction: a coined,
  distinctive mark** (easier to register + secure a domain), then a **licensed-attorney clearance**
  (federal + common-law + state) before adoption. Knockout screens are due diligence, not legal
  clearance.
- **Builds on:** ADR-0012/0020 (patient-held `share_with_clinic` consent + single server-side
  access predicate — the caregiver is a new grantee of the *same* primitive), ADR-0044/0046
  (clinician loop + non-urgent/911 framing this mirrors), ADR-0045 (Visit-Ready Summary — proxy
  entry feeds the same append-only record the Summary reads), ADR-0041 (FDA device-status
  framework), ADR-0006/0021 (research-grade provenance / PHI-free observability), ADR-0027/0031
  (retention / right-of-access), ADR-0039 (60+ accessibility).

> **This is NOT a medical-alert or emergency-response system, NOT a diagnostic tool, and NOT a
> real-time/urgent channel.** Alerts are **non-urgent** wellness-trend notifications; the copy says
> so and every alert/compose surface carries a persistent *"If this is an emergency, call 911"*
> banner (mirrors ADR-0045/0046). No fall detection, no red-flag scanning, no triage promise. The
> product is not FDA-cleared and processes synthetic data only. The **caregiver subscription is an
> out-of-pocket consumer product, not a Medicare/Medicaid-billed service** — conflating the two is
> a compliance risk this ADR exists partly to prevent.

## Context

The platform already serves **patients** and **clinicians** (with a hoped-for clinician-billed
RTM/RPM path to Medicare/Medicaid, enabler-not-biller, gated on D1/D2). A frequently-requested
third principal is the patient's **loved one** — the "sandwich-generation" adult child managing an
aging parent's diabetes/neuropathy from a distance. Their job-to-be-done is *emotional*: "I don't
know how Mom is doing between calls, and she downplays everything."

Two facts make this cheap and strategically valuable to build:
1. **It reuses a primitive we already shipped.** The caregiver is the patient-held, server-enforced,
   revocable, per-scope consent grant (ADR-0012/0020) built for clinicians — a different grantee,
   not a new mechanism.
2. **It is the one revenue line not gated on FDA/coding.** A consumer subscription needs no device
   determination and no CPT validation, so it can generate real recurring revenue *now*, while the
   reimbursement path matures behind its gates.

### Positioning & market validation (2026-07-20 research)

**Positioning: "Life360 for the medical chart."** Families already pay Life360 **$99.99/yr** for
*location* peace-of-mind about their people; this is the same emotional purchase for the *medical*
picture — which independently validates the $99/yr anchor below.

- **The pain point is documented and segment-specific.** Despite a legal right to a loved one's
  notes, **fewer than 3% of caregivers have proxy portal access**, and ~45% of hospitals don't offer
  it (they tell patients to share passwords). The gap concentrates in the **remote, working,
  sandwich-generation caregiver who isn't in the room** — 54% of US adults in their 40s are
  "sandwiched" (Pew) — which our DPN/older-adult platform naturally selects for (frequent specialist
  visits, med changes, high caregiver involvement). *Caveat:* caregivers who **are** in the room
  report decent provider communication, so the wedge is the absent/remote caregiver, not everyone.
- **Whitespace confirmed.** No mainstream competitor passively watches the EHR and pushes a caregiver
  a plain-language "a new note posted / here's what changed" alert. Portals hold the data but have
  abysmal caregiver UX (the <3%); visit-capture apps that record the appointment need someone
  physically present — useless for the remote caregiver. (Cannot prove a negative; a small startup
  may exist.)
- **Market:** ~53M US family caregivers; 55% of caregivers 50+ already use ≥1 digital tool; average
  caregiver out-of-pocket spend ~$7,242/yr — spending capacity exists (though much is
  non-discretionary; freemium gravity is real — CareZone, a paid caregiver record app, shut down in
  2023). *All figures are cited estimates from the market-research brief, not our own data.*
- **The #1 risk is onboarding friction, not demand or feasibility.** The value depends on connecting
  the caregiver to each health system's API — the same wall that has kept proxy adoption <3% for a
  decade. **The moat we must build is onboarding that is radically easier than the status quo**,
  likely by riding a records aggregator (Health Gorilla / Particle / 1up / Fasten) for multi-system
  coverage in one connect flow, rather than site-by-site EHR enablement.

## Two revenue lines (do not conflate)

| | Caregiver subscription (the caregiver app) | Clinician → Medicare/Medicaid |
|---|---|---|
| Payer | The loved one, out-of-pocket (App Store IAP) | The payer, via the servicing clinic's claim |
| What it is | Consumer software subscription | RTM/RPM remote-monitoring reimbursement |
| Reimbursed? | **No** — caregiver monitoring by a family member is not a billable clinical service | Yes (the hope), **gated** on D1 (certified coder + counsel) + D2 (FDA device) |
| Our role | Direct seller | **Enabler, not biller** (the clinic bills; we evidence) |
| Status | Buildable now | Gated / not built (ADR-0046 Phase C) |

**How they reinforce each other (the synergy, stated honestly):** the caregiver is an **adherence
and data-completeness engine**. Nudging the patient to check in and logging data by proxy produces
*more consistent data days* — exactly what RTM requires and what fills the clinician's Visit-Ready
Summary (ADR-0045). So consumer caregiver revenue and the reimbursable clinician monitoring
strengthen the same underlying record without being the same dollar. Any *clinician-billed*
caregiver-facing codes (e.g., caregiver behavior-management training / caregiver-training services /
principal-illness navigation) are a **separate, coder-validated, gated** question — **named here,
not assumed, not built**, and never a claim the caregiver subscription itself makes.

## Decision

Adopt a **caregiver principal** inside the existing codebase (one build, a new role alongside
patient / clinician / ops — **not a separate app**), sold as an individual App Store subscription.

### Relationship & consent (patient-controlled, double opt-in, instantly revocable)
- **Invite by code:** the patient shares an identifying invite code; a loved one entering it creates
  a pending link that **the patient must explicitly accept** before any data is visible (double
  opt-in). **Unlimited caregivers** per patient.
- **Patient-controlled scope, per caregiver:** the patient chooses **Trends-only** (the wellness
  score + direction, no raw data) or **Full-scope** (signals, data gaps, labs, the Visit-Ready
  Summary). Scope is the same server-side access predicate as clinician sharing (ADR-0012/0020).
- **Revocation is never blockable** (same rule as clinician access): the patient can cut a
  caregiver's access instantly; the subscription is the caregiver's, the *access* is the patient's
  to grant and revoke.
- **A caregiver is never a clinician:** no clinical authority, no write access to the record except
  proxy-with-confirm (below). All caregiver reads are audited (counts/refs, PHI-free — ADR-0021).

### Alerts (the headline feature — non-urgent by construction)
- A **small, non-urgent alert set** the patient opts into: *missed check-in* (e.g., no data in N
  days), *a logged medication change*, and *a weekly trend shift* (ties to the earlier
  med-change→weekly-trend brainstorm). Push via APNs/FCM.
- **HEADLINE alert — "New chart note after a visit."** When a new clinical note / after-visit summary
  appears in the patient's EHR, notify the caregiver: *"A new note from Dr. X was added to Dad's
  chart after Tuesday's visit — review it."* This is the market's clearest whitespace and directly
  answers the top caregiver pain point ("how did the appointment go?"). Data source: the inbound
  **FHIR `DocumentReference`** pull (ADR-0045 P2, task #27) via the patient's SMART authorization;
  detection is **poll-and-diff** (real-time FHIR `Subscription` is not broadly available to
  patient-access apps). The Cures Act information-blocking rule requires notes be released to patients
  promptly, which makes a **same-day-to-few-days** alert realistic (note *finalization* is on the
  clinician's clock, so "instant" is not promised). **Non-diagnostic guardrail: we alert on the
  *existence* of a new note and let them read it — we never interpret or summarize its clinical
  meaning.** Requires the patient's EMR scope + full-scope sharing; patient-revocable.
- **Non-urgent framing is non-negotiable:** persistent *"If this is an emergency, call 911"* banner;
  copy states alerts are periodic wellness-trend notices, not real-time monitoring. **No red-flag
  text/behavior scanning, no triage, no emergency dispatch** (interpretive/device functions and a
  promise the channel can't keep).
- Alerts respect the patient's chosen scope (Trends-only caregivers get only trend-level alerts).

### Location / whereabouts (opt-in, patient-controlled, premium — the "Life360" half)
Location closes the peace-of-mind bundle (chart visibility *and* whereabouts) and is a natural
**premium-tier** feature. It is also the **most privacy-loaded thing in this spec**, so it ships only
with these guardrails:
- **Patient-opt-in, granular, patient-revocable — we build *sharing*, not *surveillance*.** The
  tracked person is a **competent adult**, so location is the *patient's* switch, never a caregiver's.
  A dementia/guardianship (POA-gated) path is explicitly **out of launch scope**.
- **Reassurance, not rescue.** Foreground/periodic location and gentle geofence reassurance —
  *"arrived at the clinic," "home safe"* — **not** fall detection, wander-alarm, or emergency
  dispatch. The 911 framing stays; the copy never implies a safety-response service.
- **New privacy-law surface (flagged).** Precise geolocation is "sensitive data" under CCPA/CPRA, and
  Washington's **My Health My Data Act treats location near a health facility as health data** —
  which "arrived at the clinic" literally is. Location therefore lives in the same
  encrypted/consented/audited/deletable regime as all other PHI, with its own explicit consent scope.
- **App Store + technical cost.** Background location draws heavy Apple/Google review scrutiny
  (prominent disclosure + clear user benefit required), drains battery, and needs a native
  background-geolocation capability — a **native-rebuild trigger** (cf. ADR-0023). Prefer
  foreground/on-demand or coarse "arrived/home" geofences at launch over always-on precise tracking.

### Proxy data entry (at launch)
- A caregiver may **log data on the patient's behalf** (helpful for a 60+/85+ patient who won't use
  the app themselves). Entries are written to the **append-only Observation record** with
  **provenance = caregiver-proxy** and land as **preliminary**, requiring **patient confirmation**
  before they count (reuse ADR-0045's preliminary→human-confirm pattern). Proxy writes are PHI,
  ALCOA+, fully audited; they never mutate history.

### Pricing & packaging
Individual auto-renewing App Store subscriptions (Apple/Google are merchant of record — they collect
and remit sales tax/VAT). Two tiers:

| Tier | Monthly (no trial) | Annual (1 free month) |
|---|---|---|
| **Stay Connected** (trends) | $4.99 | $49.99 |
| **Stay Alerted** (full scope + alerts) | $9.99 | **$99** |

- **Free month only on the annual plans; monthly has no trial** (steers to annual — better LTV and
  cash against the fixed cost base, and kills trial-cycling; stores grant one intro offer per
  person per subscription group).
- Do **not** stack the free trial month *and* a steep baked-in annual discount — pick one clear
  offer (default: light annual discount + the free trial month).

### Cost model (fixed compliance floor dominates — get real quotes)
Unit economics are high-margin (net ≈ $4.24/yr-equiv at 15% platform fee for the base, ≈ $84/yr for
the alert tier; marginal infra pennies, push free). The real cost is the **count-independent fixed
floor** of running a PHI-handling company: **one-time ≈ $40k–150k** (legal/ToS, HIPAA risk
assessment, SOC 2 readiness+audit, pen test, FDA consultant) and **recurring ≈ $60k–200k/yr** (SOC 2
re-audit, annual pen test, compliance tooling, cyber/E&O insurance, counsel, hosting) — **excluding
salaries**. Break-even therefore depends on attribution:
- **Incremental** (platform compliance funded anyway; caregiver adds only subscription plumbing +
  consumer-subscription legal + support): **≈ 385–900 paying caregivers**.
- **Fully-loaded** (caregiver revenue must justify the whole compliant platform): **≈ 1,540–2,700**.
The right lens is incremental. **All cost figures are estimates to be replaced with real quotes.**
The two numbers that actually decide viability are **CAC** (only the patient-driven invite loop
makes acquisition math close at ~$45/yr net — paid install ads do not) and **churn** (caregiving is
episodic; the annual plan + premium tier are the defenses).

## Privacy / PHI

The patient inviting their own loved one is the patient exercising their **own right to share their
own health data** — a clean legal basis. But we hold the PHI and disclose it on the patient's
instruction, so: **explicit, granular, per-caregiver consent; instant revocation; every caregiver
access audited** (counts/refs only, PHI kept out of all structured/proxy logs — ADR-0021).
Caregiver proxy-write content and any messages are PHI under ADR-0027/0031 retention +
right-of-access. A caregiver account is a distinct identity, never a covered-entity clinician.

**Location data** carries the highest sensitivity: precise geolocation is "sensitive data" under
CCPA/CPRA and, where it reveals presence at a health facility, is **health data under Washington's
My Health My Data Act** (and similar state laws). It gets its own explicit, separately-revocable
consent scope, the same encryption/audit/deletion regime, and is minimized (prefer coarse
"arrived/home" geofences over stored precise tracks). **Inbound EMR notes** surfaced to caregivers
are the patient's own records disclosed on the patient's instruction and scope — read-only, audited,
never interpreted.

## Consequences

- **First ungated revenue line** — real recurring consumer revenue without waiting on FDA/coding.
- **Adherence/retention + data-completeness lever** — two people invested in the patient checking
  in; proxy entry increases captured Observations, which strengthens the clinician surface and the
  (separately-billed, gated) reimbursable monitoring.
- **Cheap to build** — reuses the consent primitive; the heavy lift is subscription plumbing, push
  infra, the invite/accept flow, and the tiering.
- **The gate is compliance economics, not engineering** — the fixed floor means this turns
  meaningful at hundreds-to-low-thousands of subscribers, best justified as incremental margin.
- **The #1 build risk is onboarding friction** (connecting caregivers to EHR data), not demand — the
  make-or-break is a connect flow far easier than the <3%-adoption portal status quo; plan for a
  records aggregator rather than site-by-site EHR enablement.

## Alternatives considered

- **A separate caregiver app/codebase.** Rejected — the caregiver is a role on the same build
  (one auth, one record, one consent model); "separate app" is a store/marketing framing only.
- **Caregiver as a read-only "clinician-lite" role.** Rejected — different relationship, consent
  basis, and copy; the caregiver is a patient-granted personal share, not a care-team member.
- **Bundle caregiver access into the patient's subscription.** Rejected — different payer and buyer
  (the worried adult child has the wallet and the motivation); individual App Store subs fit.
- **Position/bill it as a reimbursed service.** Rejected — caregiver monitoring by a family member
  is not a billable clinical service; keep it direct-pay and keep the reimbursed clinician path
  strictly separate and gated.

## Open questions (for the owner / reviewers)

1. **Is Trends-only a real tier or just an on-ramp** to the alert tier (which is the feature people
   actually pay for)? Decide whether to sell it or make it a free "glance" mode.
2. **Annual price points** — $49.99 / $99 as drafted, and the exact free-month vs discount
   construction.
3. **Launch alert set** — the three defaults (missed check-in, med change, weekly trend shift), or a
   different starting set.
4. **Name** — pick a coined candidate and clear it with a trademark attorney (Kinly knocked out
   2026-07-20; see the Name field).
5. **Store presence** — its own App Store listing vs an in-app upsell within the patient app (or
   both).
6. **Push infrastructure scope** — build now (needed for alerts) vs. passive-first V1.
7. **Chart-note alert dependency** — this headline feature needs the ADR-0045 P2 `DocumentReference`
   pull (#27) and likely a records aggregator; is it a launch feature or fast-follow given the
   onboarding-friction risk?
8. **Location at launch or later** — is whereabouts a launch premium feature or a V2 add? And the
   consent model for a competent adult (opt-in sharing) vs the deferred POA/guardianship path.
9. **Aggregator choice** — Health Gorilla / Particle / 1up / Fasten (or direct EHR) for multi-system
   note/record access — a build-vs-partner decision that gates the chart-note feature's reach.
