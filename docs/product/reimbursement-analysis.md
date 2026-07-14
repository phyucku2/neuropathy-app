# Reimbursement Analysis — Digital/Remote Monitoring Pathways for the Neuropathy App

**Date:** 2026-07-14
**Status:** Draft for product/design planning — **PENDING compliance validation**
**Owner action required:** certified coder + compliance/legal sign-off before any build ships or any claim is submitted.

---

> ## ⚠️ READ THIS FIRST — SCOPE & CAVEAT (top)
>
> This document is **product and design guidance to help us ENABLE billing pathways** —
> i.e. to decide what the app should *capture, build, and export* so a covered entity
> *could* later submit a compliant claim. **It is NOT billing advice, NOT legal advice,
> and NOT coding advice.** Nothing here authorizes anyone to bill Medicare, Medicaid, or
> any payer.
>
> - CPT®/HCPCS codes, coverage, day/time thresholds, supervision rules, and payment
>   rates **change at least annually** (the CY2026 Physician Fee Schedule already moved
>   several of the numbers below) and vary **by Medicare Administrative Contractor (MAC)**
>   and **by state Medicaid program**.
> - CPT® is a registered trademark of the American Medical Association; code descriptors
>   are paraphrased here, not quoted verbatim.
> - Any real claim requires validation by a **certified professional coder (CPC)** plus
>   **compliance/legal** review, and depends on the *billing clinician's* documentation,
>   medical necessity, plan of care, consent, and the device's actual FDA status — none
>   of which this app can assert on its own.
> - We are the software vendor / IP owner (ADR-0001). **BioMech Health is a licensee.**
>   Who bills, under what enrollment, and with which supervising professional is a
>   business/clinical decision outside this repo.
>
> **Treat every number below as "verify before relying on it." Every factual claim is
> sourced (see [Sources](#sources), all accessed 2026-07-14).**

---

## 1. Why this analysis, and what data we actually have

The app already captures several distinct, provenance-complete data streams (all stored
as research-grade `Observation` rows — ALCOA+, immutable, coded; ADR-0006). The
reimbursement question is: **which billing pathway does each stream plausibly fit, and
what would we need to build to make a claim *defensible*?**

| App data stream | Source / ADR | Nature | Provenance origin |
|---|---|---|---|
| BioMech balance & gait metrics (sway velocity/area, balance score, gait speed, cadence, step length, step-time symmetry) | ADR-0014 (PDF ingest V1) | Musculoskeletal / functional response | `document_imported` (V1); `device_measured` reserved for V2 API/SDK |
| ADL daily check-ins (patient-reported functional status, symptoms) | ADR-0006 | Self-reported therapeutic response | `patient_reported` |
| Labs (LOINC/UCUM, FHIR R4-aligned; e.g. HbA1c, B12) | ADR-0007, ADR-0008/0009 | Physiologic / diagnostic | `device_measured` / EMR-pulled |
| Trajectory engine output (direction/confidence/signals) | ADR-0016 | Derived, non-diagnostic | `derived` |
| Clinician surface (consent-gated panel, cross-source trend table, capability orders) | ADR-0012, ADR-0013, ADR-0016 | Care-coordination workspace | n/a |

Two facts shape everything below:

1. **Our richest, most differentiated stream is BioMech musculoskeletal/gait/balance data
   plus ADL self-report** → this is the natural fit for **RTM**, whose device codes are
   explicitly *musculoskeletal-system*, *respiratory-system*, and *cognitive behavioral
   therapy (CBT)* system data, and which — unlike RPM —
   **permits patient self-reported data**.[^hhs][^mtelehealth]
2. Our labs are **physiologic but not continuously self-measured by an FDA device in the
   patient's hand** — they are point-in-time results pulled from EMR/lab systems. That
   makes them a **poor fit for RPM's device + 16-day auto-transmission rule** (see §3).

---

## 2. RTM — Remote Therapeutic Monitoring (primary recommended pathway)

**Codes (CY2025 baseline).**[^thoroughcare][^hhs][^mtelehealth]

| Code | What it covers | Key rule |
|---|---|---|
| **98975** | Initial set-up & patient education on device use | Once per episode of care |
| **98976** | Device supply — **respiratory** system data | ≥16 days of data in 30 days |
| **98977** | Device supply — **musculoskeletal** system data | ≥16 days of data in 30 days |
| **98978** | Device supply — **cognitive behavioral therapy** data | ≥16 days of data in 30 days |
| **98980** | Treatment-management, first 20 min / calendar month | Requires ≥1 interactive communication (live, real-time, with patient/caregiver) in the month |
| **98981** | Treatment-management, each additional 20 min / month | Add-on to 98980 |

**The device must be a "medical device as defined by the FDA"** (FD&C Act §201(h)). RTM
software *can* qualify as that device (Software as a Medical Device); because the CPT code
set is maintained by the AMA and does not itself adjudicate a device's FDA status, the
burden of meeting the FDA-device definition rests on the biller/manufacturer, and payers
may add requirements.[^cms2022][^mtelehealth] **This is the single biggest gating constraint for
us:** RTM presumes the *data source* is an FDA-regulated device. For BioMech data that
turns on **BioMech's device/software regulatory status**, not ours (we ingest and graph
it; ADR-0014). For app-native ADL capture, it turns on **whether our software is itself
cleared/regulated as a device** — an FDA SaMD determination that is an owner + regulatory
decision, not something this doc can assert.

**Self-reported data is allowed for RTM** (objective device-integrated data *or*
subjective patient inputs), which is exactly what ADL check-ins are — a genuine advantage
over RPM.[^hhs][^mtelehealth] The service must be **ordered by a physician/QHP** (a physical
therapist qualifies), and the data must relate to **signs, symptoms, and function of a
therapeutic response** — again a clean match for gait/balance/ADL.[^mtelehealth]

**CY2026 change — build to this, not just 2025.** The CY2026 PFS final rule (CMS-1832-F,
effective 2026-01-01) **added new short-window device codes for 2–15 days of data**,
**revised the existing device-supply descriptors (98976/98977/98978) to a 16–30 day
window**, and **added lower treatment-management time codes** (first 10–19 min/month)
alongside the existing 20-minute codes.[^cms2026fr][^cmsmm14250][^nixon2026] The confirmed
new/revised codes, all effective **2026-01-01**, are:

- **RPM:** **99445** (device supply, 2–15 days of data in 30, paid at parity with 99454)
  and **99470** (treatment management, first 10–19 min/month). **99454 continues to require
  16+ days (unchanged).**
- **RTM:** **98984** (respiratory, 2–15 days), **98985** (musculoskeletal, 2–15 days),
  **98986** (CBT, 2–15 days), and **98979** (treatment management, first 10–19 min/month);
  the **98976 / 98977 / 98978** device-supply descriptors are revised to the **16–30 day**
  window.

The design takeaway is stable regardless: **our adherence counter must be parameterized
(2–15 vs 16–30 day tiers), not hard-coded to "16."**

### 2.1 RTM mapping — our streams → what we must build

| Our stream / feature | RTM fit | What the app must CAPTURE or BUILD for a compliant claim | Gating constraint |
|---|---|---|---|
| BioMech gait/balance metrics | **Strong** — musculoskeletal system data (98977 family) | Per-30-day **days-with-data counter** with tiered thresholds (2–15 / 16–30); each qualifying day attributable to a real transmission/upload event; billing-period boundary tracking | BioMech source must be an **FDA medical device**; V1 is `document_imported` (a parsed PDF), which is weaker evidence than `device_measured` — the V2 API/SDK path (ADR-0014, deferred) materially strengthens the claim |
| ADL daily check-ins | **Strong** — self-reported therapeutic response (RTM permits self-report) | Same ≥N-days adherence counter over ADL submissions; ensure each check-in is contemporaneous & attributable (already true, ADR-0006) | Whether **self-report-only** satisfies a given MAC's device expectation; our software's own FDA status if ADL is the "device" |
| Clinician review time | **Required for 98980/98981** | **Interactive-time logging**: a timer/ledger capturing minutes of treatment-management per clinician per patient per calendar month, plus a record of the **≥1 live interactive communication** (call/video) in the month | Time must be genuine clinician work, not app time; documentation must support it |
| 98975 set-up | Needed once per episode | A **setup/onboarding event record** (device education completed, timestamped, per episode) | Episode-of-care concept must exist in our model |
| Consent | Prerequisite | **Billing-consent capture** distinct from care/research consent (we already separate consent scopes, ADR-0006/0012) | Consent wording is an owner/legal decision |
| Export | Prerequisite | **Billing-event / documentation export** (per patient, per period: days-with-data, interactive-time total, communication timestamp, code candidates) for the biller's system — read-only, PHI-safe, audited | Not a claim submitter; an evidence packet only |

**RTM cannot be billed in the same period as RPM for the same patient.**[^thoroughcare][^hhs]

---

## 3. RPM — Remote Physiologic Monitoring (weak fit as built; note the constraints)

**Codes.**[^hhs][^acp]

| Code | Covers | Key rule |
|---|---|---|
| **99453** | Device set-up & patient education | Once per episode |
| **99454** | Device supply + daily recordings/transmission | ≥16 days in 30 days (**unchanged** in CY2026); CY2026 adds **99445** for 2–15 days of data, paid at parity[^cms2026fr][^cmsmm14250][^nixon2026] |
| **99457** | Treatment-management, first 20 min/month | ≥1 interactive communication; CY2026 lowers initial-time threshold |
| **99458** | Each additional 20 min/month | Add-on |
| **99091** | Physician data review/interpretation, 30 min | Separate pathway |

**Why our data mostly does NOT qualify today:**

- **RPM requires *physiologic* data collected and transmitted by a medical device — and
  the device must *automatically* collect and transmit; manually recorded / self-keyed
  data does NOT count.**[^hhs][^cms2021] Our labs are physiologic but arrive as EMR/lab-system
  results (point-in-time, pulled), **not** a patient-worn device auto-transmitting ≥16
  days/30. ADL is self-reported → excluded from RPM by definition.
- Therefore **labs and ADL, as currently modeled, do not satisfy RPM.** RPM only becomes
  relevant if the app ingests a **continuous physiologic device stream** (e.g. a CGM,
  BP cuff, or a wearable auto-transmitting daily) with device-supplied provenance
  (`device_measured`) and a ≥16-day cadence.

### 3.1 RPM mapping

| Our stream | RPM fit | What we'd need | Gating constraint |
|---|---|---|---|
| Labs (HbA1c, B12, …) | **No** — not device-auto-transmitted physiologic monitoring | n/a — wrong data shape | Point-in-time results, not 16-day device cadence |
| ADL check-ins | **No** — self-reported, non-device | n/a | RPM excludes manual/self-report |
| *Hypothetical* CGM / wearable stream | Possible (future) | `device_measured` provenance, auto-transmit cadence, 16-day counter, FDA device | We don't ingest such a stream today |

**Design note:** the ≥16-day adherence counter, interactive-time ledger, setup-event
record, and billing export we build for RTM are **directly reusable** for RPM if a
qualifying physiologic device stream is ever added — build them generically.

---

## 4. CCM / PCM — Chronic Care Management / Principal Care Management (complementary)

Neuropathy is typically a chronic condition managed alongside diabetes → the clinician
surface (ADR-0012/0016) is a natural home for **care-coordination** billing, which is
*separate from* device monitoring and can, in principle, be billed **concurrently** with
RTM/RPM when the time is not double-counted.

**Codes.**[^prevounce][^nsight]

| Code | Covers | Key rule |
|---|---|---|
| **99490** | Non-complex CCM, first 20 min clinical-staff time/month | ≥2 chronic conditions expected to last ≥12 mo; general supervision |
| **99439** | CCM add-on, each additional 20 min clinical-staff/month | Add-on to 99490 |
| **99491** | CCM, first 30 min personally by physician/QHP | Physician time, not staff |
| **99437** | CCM add-on, each additional 30 min physician/QHP | Add-on to 99491 |
| **99424 / 99425** | PCM, physician/QHP — first / additional 30 min | **Single** complex chronic condition expected ≥3 mo |
| **99426 / 99427** | PCM, clinical-staff — first / additional 30 min | Single complex condition |

**CCM (99490 family) and PCM (99424 family) cannot both be billed by the *same
practitioner* for the *same patient* in the *same calendar month* — but a *different*
practitioner may bill PCM (e.g. a specialist managing one condition) while another bills
CCM, each under a separate care plan.**[^cmsccmfaq][^cmsmln909188] The exclusivity is
**per-practitioner, not per-patient**; pick the right code per practitioner based on the
patient's profile. Both require a **comprehensive care plan**, patient consent, and **time
tracking**.

### 4.1 CCM/PCM mapping

| Our feature | Fit | What we'd need | Gating constraint |
|---|---|---|---|
| Clinician surface / panel (ADR-0012) | **Good** as the coordination workspace | **Care-plan artifact** (structured, editable, versioned) + **care-coordination time logging** per patient per month | Care-plan authoring is net-new surface area |
| Consent (ADR-0005/0012) | Prerequisite | Billing-consent capture (distinct scope) | Legal wording |
| Cross-source trend table (ADR-0016) | Supports the "manage chronic condition" narrative | Nothing new required to *support*; it is not itself billable | Non-diagnostic posture must hold |
| Audit/time | Prerequisite | Same interactive-time ledger pattern as RTM, tagged to CCM/PCM activity | Don't double-count time across RTM and CCM |

CCM/PCM is **lower-build, lower-differentiation** than RTM (it is care-coordination time,
not our unique gait/balance data). Recommended as a **second wave**, not first.

---

## 5. Digital therapeutics / digital mental health (note only — not our current lane)

The CY2025 PFS created HCPCS **G0552 / G0553 / G0554** for **Digital Mental Health
Treatment (DMHT) devices** — supply + treatment-management of an **FDA-cleared** (510(k)
or De Novo, under 21 CFR 882.5801; CY2026 extended to 882.5803) prescription digital
device used *incident to* a behavioral-health treatment plan.[^aapc][^noridian][^cure][^cmsmm14315]

**Relevance to us: low today.** Our product is a neuropathy monitoring/graphing tool, not
an FDA-cleared behavioral-health treatment device, and DMHT requires the app itself to be
the cleared therapeutic. If the roadmap ever adds a *cleared therapeutic* module
(e.g. a validated intervention), revisit — but **do not design toward DMHT now.** Broader
PDT/DTx Medicare coverage remains **narrow and evolving**; treat any DTx billing claim as
requiring fresh regulatory + coding review.

---

## 6. Medicaid variability (must-flag)

Everything above is **Medicare**. **Medicaid is state-by-state**: some states cover RTM/RPM
and CCM, some don't, some use different codes, modifiers, or rates, and managed-care plans
add their own rules. **No Medicaid billing assumption is portable across states.** Any
Medicaid pathway must be validated **per state** by the biller. We should build our
capture/export to be **payer-agnostic** (capture the underlying facts — days-with-data,
minutes, communications, consent — and let the biller map to the payer's codes) rather
than encoding Medicare code numbers into product logic.

---

## 7. Prioritized "reimbursement-enabling features" (build order)

Ranked for the **most defensible pathway first (RTM, given BioMech + ADL)**. **All items
are PENDING the compliance validation in the caveat — this is a build-readiness backlog,
not an instruction to bill.**

1. **Parameterized days-with-data adherence counter** (per patient, per 30-day period, per
   data stream) with **configurable tiers** (2–15 / 16–30 days) so it survives the CY2026
   threshold split. Each counted day must tie to a real, attributable
   transmission/upload/check-in event (we already have provenance; this aggregates it).
   *Serves RTM first, RPM later.*
2. **Interactive treatment-management time ledger** — per clinician, per patient, per
   calendar month: accumulated minutes + a recorded **≥1 live interactive communication**
   event with timestamp. Injected clock, immutable, audited (reuse ADR-0013 patterns; no
   wall-clock in tests). *Serves RTM 98980/98981, RPM 99457/99458, and CCM/PCM time.*
3. **Episode-of-care + setup/onboarding event** model (device education completed, once per
   episode) to support 98975 / 99453. *Small model addition.*
4. **Billing-consent capture** as a distinct consent scope (separate from care and research
   consent, which we already separate). Owner/legal owns the wording.
5. **PHI-safe billing-evidence export** — per patient/period read-only packet: days-with-
   data by stream+tier, total management minutes, communication timestamp(s), consent
   state, and **candidate** code families (clearly labeled "candidate — not a claim").
   Audited like every PHI read (ADR-0012). *This is an evidence handoff to the biller's
   system, never a claim submitter.*
6. **BioMech device-provenance strengthening** — prioritize the V2 API/SDK ingestion path
   (ADR-0014, currently deferred) because `device_measured` provenance is materially more
   defensible for RTM than `document_imported` PDF parsing.
7. **FDA-status decision record** — an ADR (owner + regulatory) resolving *whether and how*
   the app or its data sources meet the RTM "medical device as defined by the FDA" bar.
   **This gates whether RTM is billable at all** and should be answered before deep build.
8. **(Second wave) Care-plan artifact + care-coordination time** for CCM/PCM via the
   clinician surface.

**Do NOT hard-code Medicare code numbers into product logic.** Capture the underlying
billable *facts* generically; let a validated coder map facts → codes per payer/year.

---

> ## ⚠️ CAVEAT (bottom — same weight as the top)
>
> This is **product/design guidance to ENABLE billing pathways, not billing, legal, or
> coding advice.** Codes, coverage, thresholds, supervision rules, and rates **change
> annually and vary by MAC and by state Medicaid program**; the CY2026 final rule already
> moved several numbers here. **Any real claim requires validation by a certified
> professional coder plus compliance/legal**, and depends on the billing clinician's
> documentation, medical necessity, plan of care, consent, and the device's actual FDA
> status. **Nothing in this document authorizes anyone to bill any payer.** Every factual
> claim is sourced below (accessed 2026-07-14); verify against the primary CMS rule and
> your MAC/state before relying on any figure.

---

## Sources

All accessed **2026-07-14**. Secondary billing-guidance sites are used for orientation;
**primary authority is the CMS Physician Fee Schedule final rule and your MAC/state
Medicaid policy** — confirm every code and threshold there before use.

[^thoroughcare]: ThoroughCare — "Remote Therapeutic Monitoring: 2025 CPT Codes / Billing Rules." <https://www.thoroughcare.net/blog/remote-therapeutic-monitoring-billing-rules>
[^hhs]: U.S. HHS Telehealth — "Billing for remote patient monitoring" (RPM vs RTM, physiologic vs therapeutic, self-report allowed for RTM only, 16-day rule, device auto-transmission). <https://telehealth.hhs.gov/providers/best-practice-guides/telehealth-and-remote-patient-monitoring/billing-remote-patient>
[^mtelehealth]: mTelehealth — "RTM Service Codes 98975/98976/98977 & Treatment-Management 98980/98981 FAQ" (device must meet FDA §201(h); RTM device categories incl. respiratory/MSK; self-reported data allowed; ordered by physician/QHP incl. PT). <https://www.mtelehealth.com/wp-content/uploads/2022/04/Remote-Therapeutic-Monitoring-FAQs-RTM-Service-Codes-98975-98976-98977-and-RTM-Treatment-Management-Codes-98980-and-98981.pdf>
[^cms2022]: CMS / Federal Register — "Medicare Program; CY 2022 Payment Policies Under the Physician Fee Schedule" (86 FR 65112 et seq.; RTM device must meet the FDA §201(h) definition, and CPT/AMA does not adjudicate a device's FDA status — burden on biller/manufacturer). <https://www.federalregister.gov/documents/2021/11/19/2021-23972/medicare-program-cy-2022-payment-policies-under-the-physician-fee-schedule-and-other-changes-to-part>
[^acp]: American College of Physicians — "Remote Patient Monitoring Billing, Coding and Regulations" (RPM 16-day requirement; physiologic data). <https://www.acponline.org/practice-career/business-resources/telehealth-guidance-and-resources/remote-patient-monitoring-billing-coding-and-regulations-information>
[^cms2021]: CMS / Federal Register — "Medicare Program; CY 2021 Payment Policies Under the Physician Fee Schedule" (85 FR 84472 et seq.; RPM physiologic data must be electronically/automatically collected and transmitted by the device — manually self-entered data does not qualify). <https://www.federalregister.gov/documents/2020/12/28/2020-26815/medicare-program-cy-2021-payment-policies-under-the-physician-fee-schedule-and-other-changes-to-part>
[^prevounce]: Prevounce — "Rules for CPT 99490 and the other Chronic Care Management codes" (2026 CCM). <https://blog.prevounce.com/rules-for-cpt-99490-and-the-other-chronic-care-management-codes>
[^nsight]: Nsight Health — "Principal Care Management (PCM) CPT Codes 2026: Billing & Reimbursement Guide." <https://blog.nsightcare.com/blog-/principal-care-management-pcm-cpt-codes-2026-billing-reimbursement-guide>
[^cmsccmfaq]: CMS — "Chronic Care Management Services FAQs" (CCM/PCM concurrency: the *same* practitioner may not bill CCM and PCM for the same patient in the same month, but *different* practitioners may bill CCM and PCM concurrently with separate care plans). <https://www.cms.gov/files/document/chronic-care-management-faqs.pdf>
[^cmsmln909188]: CMS MLN909188 — "Chronic Care Management Services" (MLN Booklet; CCM vs PCM scope, care-plan and consent requirements, concurrency). <https://www.cms.gov/files/document/chroniccaremanagement.pdf>
[^aapc]: AAPC Knowledge Center — "Medicare Implements Digital Mental Health Treatment Codes" (G0552–G0554; FDA clearance). <https://www.aapc.com/blog/93026-medicare-implements-digital-mental-health-treatment-codes/>
[^noridian]: Noridian Medicare — "Understanding Digital Mental Health Treatments" (DMHT device / 21 CFR 882.5801). <https://med.noridianmedicare.com/web/jfa/article-detail/-/view/10529/understanding-digital-mental-health-treatments>
[^cure]: CureAdvantage — "Billing G0552 DMHT Devices: The 2025 Compliance Playbook." <https://cureadvantage.com/billing-g0552-dmht-devices-the-2025-compliance-playbook/>
[^cmsmm14315]: CMS MLN Matters MM14315 — "Medicare Physician Fee Schedule Final Rule Summary CY 2026" (primary CMS summary covering DMHT/digital-device coverage and the CY2026 remote-monitoring updates). <https://www.cms.gov/files/document/mm14315-medicare-physician-fee-schedule-final-rule-summary-cy-2026.pdf>
[^cms2026fr]: CMS / Federal Register — "Medicare and Medicaid Programs; CY 2026 Payment Policies Under the Physician Fee Schedule and Other Changes" (CMS-1832-F final rule; new 2–15-day RPM/RTM device codes, 16–30-day realignment of 98976/98977/98978, and new first-tier 10–19-minute management codes; effective 2026-01-01). <https://www.federalregister.gov/documents/2025/11/05/2025-19787/medicare-and-medicaid-programs-cy-2026-payment-policies-under-the-physician-fee-schedule-and-other>
[^cmsmm14250]: CMS MLN Matters MM14250 — "Therapy Code List: 2026 Annual Update" (confirms new/revised RTM codes 98979/98984/98985/98986 and the 16–30-day revision of 98976/98977/98978). <https://www.cms.gov/files/document/mm14250-therapy-code-list-2026-annual-update.pdf>
[^nixon2026]: Nixon Law Group — "CMS Finalizes 2026 Remote Monitoring Reimbursement Updates: What Changed for RPM and RTM" (secondary orientation: new 2–15-day device codes; 16–30-day realignment; reduced management-time thresholds). <https://www.nixonlawgroup.com/resources/cms-finalizes-2026-remote-monitoring-reimbursement-updates-what-changed-for-rpm-and-rtm>
