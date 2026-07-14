# Reimbursement Operations — How a Claim Actually Gets Paid (RTM-first)

**Date:** 2026-07-14
**Status:** Operational research to inform product + partner enablement — **PENDING compliance validation**
**Companion to:** [`reimbursement-analysis.md`](reimbursement-analysis.md) (the pathway/fit analysis).
This document is the **operational layer beneath** that analysis: given that RTM is the
lead pathway (RPM weak-fit, CCM/PCM second-wave), *how does a servicing clinic actually
enroll, document, bill, and survive an audit* — and *exactly what must our app hand them*
to make that possible? It does **not** re-derive the code tables or fit rationale; see the
analysis for those. It extends them.

---

> ## ⚠️ READ THIS FIRST — SCOPE & CAVEAT (top)
>
> **This is operational research to inform PRODUCT and PARTNER-ENABLEMENT decisions. It is
> NOT billing advice, NOT coding advice, and NOT legal advice. Nothing here authorizes
> anyone to bill Medicare, Medicaid, or any payer.**
>
> - Codes, coverage, day/time thresholds, **supervision rules**, place-of-service handling,
>   and payment rates **change at least annually** (the CY2026 Physician Fee Schedule moved
>   several numbers) and vary **by Medicare Administrative Contractor (MAC)**, **by state
>   Medicaid program**, and **by Medicare Advantage / managed-Medicaid plan**. Every rule
>   below is tagged with the year/version it comes from — verify against the *current*
>   primary source before relying on it.
> - **CPT® is a registered trademark of the AMA**; descriptors here are paraphrased, not
>   quoted verbatim.
> - **Who bills:** the **servicing clinic** (the physician/QHP and their enrolled practice)
>   bills the payer. **Our app is the enabling technology and an RTM data source — it is NOT
>   a billing entity, does NOT enroll in Medicare, and does NOT submit claims.** We produce a
>   PHI-safe evidence packet; the clinic's certified coder and billing system produce the
>   claim.
> - Every real claim requires a **certified professional coder (CPC)** plus
>   **compliance/legal** validation, the covered entity's **own enrollment and medical
>   necessity**, and a resolved **FDA device-status determination** on the data source —
>   none of which this document (or this app) can assert.
>
> **Every factual claim below is sourced with a URL and access date (all accessed
> 2026-07-14). Primary authority is the CMS rule / MLN booklet / your MAC LCD / your state
> Medicaid manual — confirm there.**

---

## 0. The actor model — who does what

The whole operational design rests on one separation of roles. Keep it crisp:

| Actor | Role in the claim | Enrolls with Medicare? | Touches a claim? |
|---|---|---|---|
| **Servicing clinic** (physician/QHP + their practice) | Orders the service, owns the patient relationship, supervises staff, documents, **bills** | **Yes** — via PECOS/CMS-855 (§HOW) | **Yes** — submits CMS-1500/837P |
| **BioMech Health** (client/licensee, ADR-0001) | Device/data manufacturer; their FDA/device status drives RTM eligibility of the underlying data | No (not as biller for our pathway) | No |
| **Our app** (IP owner) | **Enabling technology + RTM data source**: captures adherence, interactive-time, consent, provenance; **exports** a defensible evidence packet | **No** | **No** — evidence handoff only |

There *are* other commercial models in the market (vendor revenue-share, device-supplier
compensation arrangements). Those carry their own fraud-and-abuse/AKS exposure and are a
business+legal decision **outside this repo** — noted here only so the reader knows we are
deliberately centering the **clinic-bills / app-enables** model, not those.

---

## WHO — who may bill, and under what supervision

### WHO may bill (the servicing professional)

- **RTM** codes are billed by **physicians and other qualified health care professionals
  (QHPs)**. Critically for our musculoskeletal/gait data, CMS lets **physical therapists
  and occupational therapists** bill RTM (e.g. 98977 device supply, 98980/98981 management),
  and CMS designated RTM as **"sometimes therapy"** — so it can be furnished *outside* a
  therapy plan of care when performed by a physician/QHP, or *within* one (then it carries a
  therapy modifier — **GP** physical therapy, **GO** occupational therapy, **GN** speech).
  [^cmstherapy][^apta][^foley]
- **RPM** is billed by physicians/QHPs; because RPM monitors *physiologic* data it is not a
  natural PT/OT service the way RTM is. [^cmsrpm][^foley]
- **CCM / PCM** are billed by a single physician/QHP practice per patient per month, with
  clinical-staff time counting under that practice (see supervision). [^cmsccmfaq][^cmsccmbooklet]

### The patient-relationship / "established patient" requirement

- **RPM requires an established patient relationship.** The PHE waiver of this requirement
  **ended with the PHE on 2023-05-11**; patients who *started* RPM during the PHE were
  grandfathered, but any **new** patient after that date must have an initiating visit
  (typically a new-patient E/M) to establish the relationship **before** RPM enrollment.
  [^foley]
- **RTM has no express "established patient" requirement**, but CMS expects RTM to be
  furnished in the context of an **established treatment plan** — i.e. there is a clinical
  relationship and a therapeutic goal the monitoring supports. Treat "there is a real,
  documented clinical relationship + order" as the operational bar for RTM too. [^foley]
- **App implication:** our onboarding/episode-of-care event (analysis §7 item 3) should
  record that an **initiating clinical encounter/order exists** (a reference/flag, not the
  visit note itself — the clinic owns that) so the evidence packet can attest the
  relationship predates monitoring.

### SUPERVISION — the rule that has actually changed

- **All RTM services may be furnished under GENERAL supervision** (finalized in the CY2023
  PFS and carried forward) — the billing physician/QHP need **not** be in the same building
  while clinical staff perform the work, provided the usual **"incident-to"** conditions are
  met. This is what makes it operationally feasible for auxiliary/clinical staff to run the
  monitoring day-to-day. [^nixon2023][^foley][^cmsrpm]
- **CY2024** extended **general** (not direct) supervision to **PTAs and OTAs** furnishing
  RTM in private practice (42 C.F.R. §§ 410.59, 410.60), and folded RPM/RTM into the general
  care-management code **G0511** when furnished by **RHCs/FQHCs**. [^cms2024fs][^cms2024mm][^foley]
- **"Incident-to" nuance for clinical-staff time:** when clinical staff (not the
  physician/QHP personally) perform RTM/RPM management, the time is billable under the
  billing practitioner's number **only if** the incident-to conditions hold (general
  supervision + the practitioner's active involvement in the patient's care). Consent may be
  obtained by **auxiliary personnel under general supervision**. [^cmsrpm][^foley]
- **Contrast (build the distinction in):** **CCM** clinical-staff time (99490/99439) is
  "directed by" the physician/QHP under general supervision; **PCM clinical-staff** codes
  (99426/99427) likewise; but the **physician-time** CCM/PCM codes (99491/99437, 99424/99425)
  require the professional's *own* time. Our time ledger must therefore tag **whose** minutes
  they are (physician/QHP vs clinical staff) — the code family depends on it. [^cmsccmbooklet]

### The app / vendor's non-billing enabling role, and the FDA device gate

- Our app **does not bill and does not enroll.** It is (a) the **enabling technology** the
  clinic uses and (b) potentially an **RTM data source**.
- **The FDA "medical device" requirement lands on the DATA SOURCE.** RTM (and RPM) presume
  the data comes from a **"medical device as defined by the FDA"** — the FD&C Act **§201(h)**
  definition. CMS/AMA do **not** adjudicate a device's FDA status; the burden is on the
  biller/manufacturer, and CMS confirms the device must **meet the FDA definition and
  digitally upload data**. [^cmsrpm][^cms2022fr]
  - For **BioMech gait/balance data**, FDA status turns on **BioMech's** device/software
    regulatory posture, not ours (we ingest and graph it; ADR-0014). V1 provenance is
    `document_imported` (parsed PDF) — weaker than the V2 `device_measured` path.
  - For **app-native ADL capture**, it turns on **whether our software is itself a regulated
    SaMD**. RTM *permits self-reported data*, which helps ADL fit, but does not by itself
    resolve the device question.
  - **This is a determination only the covered entity + FDA/regulatory counsel can make**
    (analysis §7 item 7). It **gates whether RTM is billable at all** and belongs in an ADR
    before deep build. Flag, don't assert.

---

## WHAT — the deliverables a compliant claim needs (per code family)

A claim is only as good as the artifacts behind it. For each family, the required
deliverable and **what our app must capture/produce** (tying to the analysis §7 backlog):

| Deliverable | Required for | What the clinic must have | What OUR APP must capture/produce |
|---|---|---|---|
| **Physician/QHP order** | RTM, RPM (setup + ongoing) | A documented order to initiate monitoring; for RTM a **new order** is needed once prior treatment goals are met before re-reporting | An **episode/setup event** referencing that an order exists (flag + timestamp + ordering-provider reference), not the order text itself [^rtmconsent][^foley] |
| **Patient consent** | RTM, RPM, CCM, PCM | **Verbal or written**, obtained in advance or at time of service, **documented in the record**; may be obtained by auxiliary personnel under general supervision. CCM/PCM consent must disclose cost-sharing, "only one practitioner bills per month," and the right to stop | **Billing-consent capture** as a distinct scope (separate from care/research consent — ADR-0006/0012): who consented, when, scope, verbal/written, version [^rtmconsent][^cmsccmfaq] |
| **Device-supplied data ≥ threshold** | RTM device (98976/98977/98978 + new 2–15-day 98984/98985/98986); RPM 99454 / new 99445 | Proof the device supplied data on the required number of days in the 30-day window; **retain the raw transmission log, not just a summary** | **Parameterized days-with-data counter** (tiers 2–15 / 16–30) per patient/stream/period, each day tied to a real, attributable upload/check-in event with provenance (analysis §7 item 1) [^cmsrpm][^denials] |
| **Interactive management time** | RTM 98980/98981 (20-min) + new 98979 (10–19-min); RPM 99457/99458 + new 99470; CCM/PCM time | A **time log** with **date, duration, and activity description** per calendar month, plus evidence of **≥1 live interactive communication** with patient/caregiver in the month | **Interactive-time ledger** (per clinician, per patient, per calendar month): accrued minutes, actor role (physician vs clinical staff), and a recorded live-communication event with timestamp; injected clock, immutable, audited (analysis §7 item 2) [^foley][^denials] |
| **Comprehensive care plan** | **CCM / PCM** (not RTM/RPM) | A structured, patient-centered, **living** care plan in the record; 24/7 access to a practitioner for urgent needs | **Care-plan artifact** (structured, editable, versioned) + care-coordination time tagged to CCM/PCM (analysis §7 item 8) [^cmsccmbooklet] |
| **Diagnosis / medical necessity** | all | ICD-10 linking the monitoring to the condition (see WHERE/HOW); documented medical necessity | Ensure the export surfaces the **candidate diagnosis context** the clinic maps (never asserts the code) |
| **Evidence export** | operational prerequisite | A defensible, auditable packet to feed the biller | **PHI-safe billing-evidence export** — read-only, audited, "candidate — not a claim" labeled (analysis §7 item 5); see the export contract in HOW |

**Do not let the app assert codes.** It captures the *facts* (days, minutes, communications,
consent, provenance); a validated coder maps facts → codes per payer/year (analysis §7).

---

## WHEN — cadence and timing rules

- **Device-data threshold window (30 days).**
  - Legacy/standard: **≥16 days of data in 30 days** for the device-supply codes
    (RPM **99454**; RTM **98976/98977/98978**, whose descriptors CY2026 revised to a
    **16–30-day** window). [^cmsrpm][^foley]
  - **CY2026 short-window codes:** **2–15 days of data in 30 days** now bill via new codes
    (RPM **99445**; RTM **98984/98985/98986**), effective **2026-01-01**. The CMS RPM page now
    states devices must "collect and transmit at least **2 days every 30 days**." [^cmsrpm][^cms2026fr]
    → **Our counter must be tiered (2–15 vs 16–30), never hard-coded to "16."**
- **Time codes are calendar-month based**, and the **16-day rule does NOT apply to them.**
  Management codes (RTM 98979/98980/98981; RPM 99457/99458/99470; CCM/PCM time) accrue
  **minutes within a calendar month** and require **≥1 interactive communication** in that
  month. [^foley]
- **Device-supply code frequency:** billed **once per 30-day period** (not more often); do
  not stack multiple device-supply codes for the same window. [^cmsrpm][^denials]
- **Setup vs monthly management:** **setup/education** (RTM 98975; RPM 99453) is billed
  **once per episode of care**, not monthly; ongoing device-supply + management are the
  recurring codes. A **new episode/new order** is required to re-report setup after goals are
  met. [^rtmconsent][^foley]
- **Mutual-exclusivity timing:** **RTM management (98980/98981) may not be reported with RPM
  management (99457/99458) for the same patient**, and generally **only one practitioner**
  bills RPM *or* RTM for a given patient in a 30-day period — a per-period, per-patient
  guard our aggregation must respect. [^foley]
- **Documentation retention / lookback:** CMS's floor is generally **7 years** for medical
  records; **Medicare Advantage / managed-care and ACO** contexts require **10 years**; the
  **federal False Claims Act** exposure runs up to **10 years**; and **state law or the
  longer of state/federal** governs. Retain the **raw device-transmission logs** for the full
  period (auditors ask for raw data, not summaries). **Plan for 10 years** unless counsel says
  otherwise. [^cmsrecords][^denials]

---

## WHERE — sites, MAC jurisdictions, and Medicaid verification

### Place of service — RPM/RTM are NOT "telehealth"

- CMS classifies RPM and RTM as **care-management services, not Medicare telehealth**
  services under §1834(m). Consequently the **telehealth geographic and originating-site
  restrictions do NOT apply** — the **patient's home is fine**, nationwide. [^cmsrpm][^rtmnottelehealth]
- Because they are not telehealth, they are billed with the **practitioner's normal place of
  service** (commonly **POS 11, office**) rather than a telehealth POS; **some payers/plans
  differ** and may expect POS 10 (telehealth-in-home) or 02. **This is a per-payer/MAC
  verification**, not a fixed value to hard-code. [^rtmnottelehealth]

### MAC jurisdictions and LCDs/articles

- Every state maps to an **A/B MAC** that processes Part B claims and can publish **Local
  Coverage Determinations (LCDs)** and **billing/coding articles** that add local
  documentation or coverage requirements on top of national policy. [^cmsmacs][^cmsmacmap]
- **How the clinic finds its MAC + policy** (put this in onboarding):
  1. CMS **"Who are the MACs"** page and the **A/B MAC jurisdiction map** → identify the MAC
     for the practice's state. [^cmsmacs][^cmsmacmap]
  2. Search the **Medicare Coverage Database (MCD)** and the MAC's own site for **RTM/RPM
     LCDs and articles** — check for local documentation, frequency, or diagnosis
     requirements beyond national rules.
  3. Re-check at least annually and when the PFS updates.

### Medicaid — a STATE-AGNOSTIC verification framework (coverage genuinely varies)

Medicaid is **state-administered**; coverage of RTM/RPM/CCM is **not uniform**. As of April
2026, CCHP counts roughly **41 states** with *some* Medicaid RPM reimbursement — meaning
**several states cover none**, and among those that cover, codes, modifiers, rates, eligible
conditions, and eligible providers **differ**; **managed-care (MCO) plans add another layer**
on top of fee-for-service (FFS). **No Medicare assumption is portable to Medicaid, and no
one state's rule is portable to another.** [^cchp][^tenovi][^medicaidgov]

**Give operators a METHOD, not a table. For ANY state, verify — in this order:**

1. **State Medicaid provider manual / policy** — does it cover RTM and/or RPM and/or CCM at
   all? Under what benefit category (some cover RPM but not RTM)?
2. **State Medicaid fee schedule** — are the specific CPT/HCPCS codes listed with a payable
   rate? A code absent from the fee schedule is effectively non-covered under FFS.
3. **Coverage conditions** — eligible diagnoses/conditions (some states limit RPM to specific
   chronic conditions), eligible provider types, prior-authorization, consent, and modifier
   rules.
4. **Managed-care plan policies** — if the member is in an MCO, the **plan's** policy (not
   just state FFS) governs; verify per plan.
5. **Cross-check with CCHP** (Center for Connected Health Policy) as an orientation index of
   state telehealth/RPM policy, then confirm against the **primary** state manual/fee
   schedule. [^cchp][^tenovi]

**App implication:** keep capture/export **payer-agnostic** — record the underlying facts
(days-with-data by tier, minutes, communications, consent, provenance, diagnosis context) and
let the biller map to whatever the state/plan pays. Do **not** encode Medicare code numbers
into product logic (analysis §6, §7).

---

## HOW — the mechanics, end to end

### 1) Enrollment (the CLINIC enrolls; the app does not)

- The servicing clinic/professional enrolls in Medicare via **PECOS** (Provider Enrollment,
  Chain, and Ownership System) using the appropriate **CMS-855** application:
  - **CMS-855I** — individual physician/NPP (and, now that **CMS-855R was discontinued**,
    the vehicle for **reassigning** benefits to a group). [^cmsenroll][^cms855i]
  - **CMS-855B** — the **group practice / organizational supplier**. [^cmsenroll]
- Prerequisite: an **NPI** from **NPPES**, with the correct **taxonomy** for the specialty;
  the NPI is furnished on the enrollment application. Physicians/NPPs and their organizations
  **pay no application fee**; PECOS processing typically runs **~45–90 days**. [^cmsenroll]
- **The app never appears in this flow.** It is not a supplier, not a reassignee, not on the
  claim. (If a future *business* model made the app a billing agent or device supplier, that
  is a separate enrollment/AKS analysis — out of scope, owner+counsel decision.)

### 2) The claim itself

- Professional services bill on the **Form CMS-1500** (paper, where allowed) or the
  **ASC X12N 837P** electronic transaction (HIPAA 5010A1) — the NUCC-maintained professional
  claim. Each MAC publishes an **837P companion guide**. [^cms1500]
- The claim carries: the **CPT/HCPCS code(s)** for the code family billed (setup / device /
  management), any **modifiers** (e.g. therapy **GP/GO/GN** when RTM is under a therapy plan;
  payer-specific telehealth/place modifiers if a plan requires them), the **ICD-10 diagnosis**
  establishing medical necessity, and the servicing/ billing provider identifiers.
- **ICD-10 linkage for neuropathy** (the coder chooses; app never asserts): diabetic
  polyneuropathy uses the **combination code E11.42** (type 2 diabetes *with* diabetic
  polyneuropathy) — and CMS/coding guidance says **do not also code G62.x** when the diabetic
  combination code applies; non-diabetic polyneuropathy uses **G62.x** (e.g. G62.9), hereditary
  forms **G60.x**. Diabetes and neuropathy documented **without an explicit link** is a known
  **audit risk** — the record must show the linkage. [^aapc][^icd10]

### 3) Consent capture + retention

- Capture **billing consent** as a distinct scope (ADR-0006/0012 already separate consent
  scopes), recording modality (verbal/written), timestamp, version, and — for CCM/PCM — the
  three required disclosures (cost-sharing applies; only one practitioner bills per month;
  right to stop). Consent may be taken by auxiliary staff under general supervision.
  [^rtmconsent][^cmsccmfaq]
- Retain consent + all supporting artifacts for the retention window (§WHEN) — **plan 10
  years**.

### 4) Documentation that survives an AUDIT (and the top denial reasons)

CMS/MACs and OIG actively audit remote-monitoring claims; OIG has flagged that many RPM
claims **lack documented interactive communication**. The recurring **denial/audit findings**
— design the export to pre-empt each: [^denials][^cmsrpm]

1. **Device-day threshold not met** — billing 99454 (or the RTM device codes) without the
   required days; **#1 finding is no raw 16-day (now tiered) transmission log.**
2. **Missing/incomplete consent.**
3. **Absent or expired physician order.**
4. **Time logs lacking specifics** — no date, duration, or activity description; **copy-pasted
   month-to-month notes** are easy to flag and hard to defend.
5. **No qualifying diagnosis / medical necessity** (e.g. neuropathy–diabetes link missing).
6. **No established patient-provider relationship** (esp. RPM).
7. **Duplicate/mutually-exclusive billing** — RPM + RTM same patient same month; two
   practitioners billing the same monitoring period.

### 5) WHAT OUR APP EXPORTS — the evidence-packet contract (the must-provide)

The single most load-bearing product commitment here. The app produces a **read-only,
audited, PHI-safe billing-evidence packet** (analysis §7 item 5) — an **evidence handoff, not
a claim**. Per patient, per billing period it MUST provide:

- **Days-with-data** by **stream** and **tier** (2–15 / 16–30), with **each qualifying day
  tied to an attributable transmission/check-in event** (raw, not just a count) — so the
  clinic can prove the threshold with underlying data.
- **Provenance** per datum (`device_measured` vs `document_imported` vs `patient_reported`;
  source system/version) — the RTM device-status evidence.
- **Interactive-management minutes**, itemized by **date, duration, activity, and actor role**
  (physician/QHP vs clinical staff), plus the **≥1 live interactive-communication event** with
  timestamp.
- **Setup/episode event** (device education completed; order-exists flag + ordering-provider
  reference; once per episode).
- **Consent state** — scope, modality (verbal/written), version, timestamp; CCM/PCM
  disclosures where relevant.
- **Diagnosis context** the clinic can map (never an asserted code).
- **Candidate code families**, explicitly labeled **"candidate — not a claim, pending
  certified-coder validation."**
- **Mutual-exclusivity flags** — surface when RPM and RTM (or two practitioners) would collide
  in a period so the biller catches it *before* submission.
- **Audit trail** — the packet's own generation is logged like every PHI read (ADR-0012);
  underlying raw transmission logs are retained per the retention window.

What the packet must **NOT** do: submit a claim, assert a final code, assert FDA device
status, or assert medical necessity. Those are the clinic's/coder's/counsel's.

### 6) Clinic onboarding + first-claim — a concrete operational sequence

1. **Enrollment confirmed** — clinic is Medicare-enrolled (PECOS/CMS-855), has NPI+taxonomy;
   identify the **MAC** and pull its **RTM/RPM LCD/articles**; if Medicaid, run the **state
   verification framework** (and MCO plan check). *(Clinic + our onboarding checklist.)*
2. **FDA device-status determination on record** — the covered entity + counsel resolve whether
   the BioMech data source / our SaMD meets §201(h). **Gate: no RTM billing posture without
   this.** *(Owner/counsel; ADR.)*
3. **Establish the patient relationship + order** — initiating clinical encounter; documented
   order to begin monitoring with a therapeutic goal. *(Clinic.)*
4. **Capture billing consent** (distinct scope) and **setup/education event** (98975/99453
   territory). *(App captures; clinic bills setup once per episode.)*
5. **Monitoring runs** — the app accrues **days-with-data** (tiered) and, when clinical staff
   review/communicate, the **interactive-time ledger** logs minutes + the live-communication
   event. *(App; clinic performs the clinical work.)*
6. **Period close** — at month/period end the app generates the **evidence packet** (§HOW-5).
7. **Coder validates + claim submitted** — the clinic's **certified coder** maps facts →
   codes, checks mutual-exclusivity and MAC/state rules, and submits **CMS-1500/837P**. *(Clinic;
   the app never submits.)*
8. **Retain** all artifacts + raw transmission logs for the retention window (plan 10 years).

---

## Open questions only compliance/coding/counsel can resolve

These are **determinations this document and this app cannot make** — they gate real billing:

1. **FDA device status of the data source** — does BioMech's device/software and/or our
   SaMD meet the FD&C Act **§201(h)** "medical device" definition for RTM? (Owner + FDA/
   regulatory counsel; ADR.) **This gates whether RTM is billable at all.**
2. **Whether ADL self-report alone** satisfies a given MAC's/plan's RTM expectation.
3. **The specific CPT/HCPCS codes, modifiers, and POS** for each real scenario, year, MAC, and
   payer — a **certified coder** call, not the app's.
4. **Medicaid coverage per state + per MCO plan** — verified case by case via the framework
   above; genuinely varies and some states cover nothing.
5. **Supervision/incident-to fit** for the clinic's actual staffing model.
6. **Consent wording** and the CCM/PCM disclosure language — legal.
7. **Retention period** applicable to the clinic (7 vs 10 vs longer under state law).

---

> ## ⚠️ CAVEAT (bottom — same weight as the top)
>
> **This is operational research to inform PRODUCT + PARTNER ENABLEMENT — NOT billing, coding,
> or legal advice. Nothing here authorizes anyone to bill any payer.** Codes, coverage, day/
> time thresholds, **supervision rules**, place-of-service handling, and rates **change
> annually and vary by MAC, by state Medicaid program, and by Medicare Advantage / managed-care
> plan** (cite the year of every rule — CY2026 already moved several). Every real claim requires
> a **certified professional coder + compliance/legal validation**, the covered entity's **own
> enrollment and medical necessity**, and a resolved **FDA device-status determination** on the
> data source. **Our app is the enabling technology and an RTM data source — it does not enroll,
> does not bill, and does not submit claims.** Every factual claim above is sourced below
> (accessed 2026-07-14); verify against the primary CMS rule / MLN booklet / your MAC LCD / your
> state Medicaid manual before relying on any figure.

---

## Sources

All accessed **2026-07-14**. **Primary authority is the CMS rule / MLN booklet / your MAC LCD /
your state Medicaid manual.** Secondary law-firm/association/vendor sources are used for
orientation and are labeled as such; confirm every code, threshold, and supervision rule
against the primary source before use.

**Primary — CMS / federal**

[^cmsrpm]: CMS — "Remote Patient Monitoring" coverage page (RPM/RTM as care management; device must meet the FDA medical-device definition and digitally upload data; collect/transmit **at least 2 days every 30 days**; setup + device + management components). <https://www.cms.gov/medicare/coverage/telehealth/remote-patient-monitoring>
[^cmsmln901705]: CMS **MLN901705** — "Telehealth & Remote Monitoring" booklet (**December 2025** version), the current CMS provider booklet covering telehealth vs. remote-monitoring billing. Landing: <https://www.cms.gov/outreach-and-education/medicare-learning-network-mln/mlnproducts/mln-publications-items/cms1243327> · PDF: <https://www.cms.gov/files/document/mln901705-telehealth-remote-monitoring.pdf>
[^cms2024fs]: CMS — "Calendar Year (CY) 2024 Medicare Physician Fee Schedule Final Rule" fact sheet (**general** supervision of PTAs/OTAs for RTM in private practice; RPM/RTM included in **G0511** for RHCs/FQHCs). <https://www.cms.gov/newsroom/fact-sheets/calendar-year-cy-2024-medicare-physician-fee-schedule-final-rule>
[^cms2024mm]: CMS **MM13452** — "Medicare Physician Fee Schedule Final Rule Summary CY 2024." <https://www.cms.gov/files/document/mm13452-medicare-physician-fee-schedule-final-rule-summary-cy-2024.pdf>
[^cms2022fr]: CMS / Federal Register — "Medicare Program; CY 2022 Payment Policies Under the Physician Fee Schedule" (86 FR 65112 et seq.; RTM device must meet the FDA **§201(h)** definition; CPT/AMA does not adjudicate a device's FDA status — burden on biller/manufacturer). <https://www.federalregister.gov/documents/2021/11/19/2021-23972/medicare-program-cy-2022-payment-policies-under-the-physician-fee-schedule-and-other-changes-to-part>
[^cms2026fr]: CMS / Federal Register — "Medicare and Medicaid Programs; CY 2026 Payment Policies Under the Physician Fee Schedule" (CMS-1832-F; new 2–15-day RPM/RTM device codes 99445 / 98984 / 98985 / 98986, 16–30-day realignment of 98976/98977/98978, new 10–19-min management codes; effective 2026-01-01). <https://www.federalregister.gov/documents/2025/11/05/2025-19787/medicare-and-medicaid-programs-cy-2026-payment-policies-under-the-physician-fee-schedule-and-other>
[^cmstherapy]: CMS — "Therapy Services" (RTM as "sometimes therapy"; therapy plan-of-care and modifier context for PT/OT/SLP). <https://www.cms.gov/medicare/coding-billing/therapy-services>
[^cmsccmfaq]: CMS — "Chronic Care Management Services FAQs" (consent once / again on practitioner change; verbal or written; per-practitioner-per-month exclusivity; disclosures). <https://www.cms.gov/files/document/chronic-care-management-faqs.pdf>
[^cmsccmbooklet]: CMS **MLN909188** — "Chronic Care Management Services" booklet (comprehensive care plan, 24/7 access, consent, clinical-staff vs physician time). <https://www.cms.gov/files/document/chroniccaremanagement.pdf>
[^cmsenroll]: CMS **MLN9658742** — "Medicare Provider Enrollment" (PECOS; CMS-855I individual/reassignment, CMS-855B group; NPI prerequisite; no fee for physicians/NPPs; processing timelines). <https://www.cms.gov/Outreach-and-Education/Medicare-Learning-Network-MLN/MLNProducts/EnrollmentResources/provider-resources/provider-enrolment/Med-Prov-Enroll-MLN9658742.html> · PECOS portal: <https://pecos.cms.hhs.gov/>
[^cms855i]: CMS — "CMS-855I Medicare Enrollment Application" (individual physician/NPP). <https://www.cms.gov/medicare/cms-forms/cms-forms/downloads/cms855i.pdf>
[^cms1500]: CMS **MLN006976** — "Medicare Billing: CMS-1500 & 837P" (**December 2025**; Form CMS-1500 paper claim, ASC X12N 837P 5010A1 electronic professional claim; NUCC-maintained; MAC 837P companion guides). <https://www.cms.gov/files/document/mln006976-medicare-billing-cms-1500-837p.pdf>
[^cmsmacs]: CMS — "Who are the MACs" (A/B MAC jurisdictions process Part B claims; publish LCDs). <https://www.cms.gov/medicare/coding-billing/medicare-administrative-contractors-macs/who-are-macs>
[^cmsmacmap]: CMS — "A/B MAC Jurisdictions" map (find your MAC by state). <https://www.cms.gov/files/document/ab-jurisdiction-map03282023pdf.pdf>
[^cmsrecords]: CMS **MLN4840534** — "Medical Record Maintenance & Access Requirements" (record-retention floor; longer for MA/managed care and by state law). <https://www.cms.gov/files/document/mln4840534-medical-record-maintenance-access-requirements.pdf>
[^medicaidgov]: Medicaid.gov — "Ensuring Access to Medicaid Services" FFS provider-rule guidance (Medicaid is state-administered; access/coverage set at state level). <https://www.medicaid.gov/medicaid/access-care/downloads/ffs-prov-final-rule-guidance.pdf>

**Secondary — orientation only (verify against primary above)**

[^foley]: Foley & Lardner — "Top 5 Rules for Medicare 2024 RPM/RTM" (established-patient requirement resumed 2023-05-11 w/ grandfathering; 16-day applies to device/setup codes not time codes; PTA/OTA general supervision under 42 C.F.R. §§ 410.59/410.60; RTM 98980/98981 not with RPM 99457/99458; one practitioner per 30-day period). <https://www.foley.com/insights/publications/2023/11/top-5-rules-medicare-2024-rpm-rtm/>
[^nixon2023]: Nixon Law Group — "General Supervision for all RTM" (CY2023 PFS finalized general supervision for RTM). <https://nixonlawgroup.com/nlg-blog/2022/11/7/key-takeaways-for-remote-therapeutic-monitoring-in-the-final-2023-medicare-physician-fee-schedule-general-supervision-for-all-rtm>
[^apta]: APTA — "Practice Advisory: Remote Therapeutic Monitoring Codes Under Medicare" (PT/OT eligibility, therapy modifiers, plan-of-care context). <https://www.apta.org/contentassets/95321a10e951408db650e2f19b96699f/apta-practice-advisory-rtm-codes032023.pdf>
[^rtmconsent]: UTHealth — Healthcare Billing Compliance, "Remote Therapeutic Monitoring (RTM)" (consent verbal/written and documented; new order after goals met; order documented in record). <https://med.uth.edu/mshbc/digital-health-services/remote-therapeutic-monitoring-rtm/>
[^rtmnottelehealth]: DrKumo — "Understanding RTM Codes and Compliance" (RTM/RPM are care-management, not §1834(m) telehealth; originating-site/geographic restrictions do not apply; POS handling varies by payer). <https://drkumo.com/understanding-rtm-codes-and-compliance-in-2025-what-providers-should-know/>
[^denials]: Phyxup Health — "RTM Claim Denials: 5 Preventable Errors" and CCNHealth — "RPM Compliance Checklist 2026" (top denial reasons; retain raw transmission logs; time-log specificity; OIG concern on missing interactive communication). <https://blog.phyxuphealth.com/rtm-claim-denials-2026/> · <https://ccnhealth.com/articles/blog/rpm-compliance-checklist-2026>
[^cchp]: Center for Connected Health Policy — "Remote Patient Monitoring" state policy index (~41 states with some Medicaid RPM reimbursement as of Apr 2026; not universal; FFS vs MCO). <https://www.cchpca.org/topic/remote-patient-monitoring/>
[^tenovi]: Tenovi — "Medicaid Remote Patient Monitoring: A State-by-State Guide" (state variation; verify state manual/fee schedule). <https://www.tenovi.com/medicaid-remote-patient-monitoring-by-state/>
[^aapc]: AAPC — ICD-10 "E11.42" (type 2 diabetes with diabetic polyneuropathy combination code). <https://www.aapc.com/codes/icd-10-codes/E11.42>
[^icd10]: Billing Care Solutions — "Peripheral Neuropathy ICD-10 Diagnosis Codes Overview" (E11.42 combination code; do not separately code G62.x when diabetic combination applies; G60/G62 usage; diabetes–neuropathy linkage audit risk). <https://billingcaresolutions.com/articles/peripheral-neuropathy-icd-10-diagnosis-codes-overview/>
