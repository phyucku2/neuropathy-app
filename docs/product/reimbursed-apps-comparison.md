# Products Already Being Reimbursed — Review & Comparison

**Date:** 2026-07-14 (all URLs accessed this date)
**Status:** Market research to inform the Wave 4 RTM-first build — **PENDING the same
compliance validation as everything else in this folder**
**Companions:** [`reimbursement-analysis.md`](reimbursement-analysis.md) (code pathways),
[`reimbursement-operations.md`](reimbursement-operations.md) (claim mechanics),
[`reimbursement-signoff-packet.md`](reimbursement-signoff-packet.md) (the professional
review packet this document feeds).

---

> ## ⚠️ READ THIS FIRST — SCOPE & CAVEAT
>
> This is **decision-support market research. It is NOT billing advice, NOT coding advice,
> and NOT legal advice**, and nothing here authorizes anyone to bill any payer. Third-party
> product facts below are what the cited public sources said on 2026-07-14 — vendors change
> claims, codes change annually, and a vendor documenting a CPT® code does **not** mean any
> particular claim by any particular provider was paid or compliant. CPT® is a registered
> trademark of the AMA. Reimbursement amounts quoted from vendor pages are the vendors'
> published estimates, not payable rates. All examples involving our own app are synthetic.
> US market only.

---

## 1. Scope and method

**Question:** which digital-health products are *actually* being reimbursed today under
RTM (98975–98981, plus 2026's 98979/98984/98985), RPM (99453–99458, plus 2026's
99445/99470), or adjacent codes — and what do they have that we don't?

**Verification standard used below:**

- **BILLING-VERIFIED** = the vendor publishes its own billing/CPT documentation (a billing
  guide, CPT sheet, or help-center article naming the codes its customers bill), or payer
  guidance names the product. Marketing copy saying "reimbursable" does **not** count.
- **BILLING-UNVERIFIED** = only marketing copy, or the company's revenue demonstrably does
  not flow through these CPT codes.
- **FDA status** was checked against FDA's databases (510(k) database and Establishment
  Registration & Device Listing, via accessdata.fda.gov and the openFDA API mirror
  api.fda.gov), never taken from vendor claims alone. "FDA-cleared" (a granted 510(k)) and
  "FDA-registered/listed" (self-registration under a 510(k)-exempt product code — no FDA
  review) are **different things** and are labeled precisely below.

Nine products were reviewed: six MSK/movement products (Limber Health, Exer AI, OneStep,
Plethy Recupe, Hinge Health, Sword Health), the closest balance-testing analog (Sway
Medical), and two general RPM/care-management enablement platforms (Optimize Health/Vivo
Care, Carium).

## 2. The provider-enabler MSK RTM platforms (billing-verified)

These are the products whose customers demonstrably bill the exact RTM code family our
Wave 4 analysis targets. All three are **enabler-not-biller** models like ours: the
clinic/therapist bills; the vendor supplies monitoring software plus billing evidence.

### 2.1 Limber Health

- **What it does:** software-only hybrid-care MSK platform for rehab-therapy practices and
  physician groups — digital home-exercise programs (7,000+ videos), RTM, PRO collection,
  and a CMS-approved QCDR/MIPS registry. No hardware.
  [limberhealth.com/frequently-asked-questions](https://www.limberhealth.com/frequently-asked-questions)
- **Data captured:** pain scores, exercise-adherence/compliance data, and outcome measures
  (PROs) logged in the patient app — i.e., predominantly **self-reported therapeutic
  response**, the same category as our ADL stream. No motion-sensor/camera kinematics
  found.
- **Codes billed — BILLING-VERIFIED (the strongest vendor CPT documentation found):** RTM
  **98975, 98977, 98980, 98981**, plus the new 2026 codes **98985** (2–15-day device
  supply) and **98979** (10–19-min management), with published 2026 national-average
  Medicare estimates (~$21.71 for 98975 up to ~$54.11 for 98980).
  [FAQ](https://www.limberhealth.com/frequently-asked-questions) ·
  [billing guide](https://www.limberhealth.com/blog/remote-therapeutic-monitoring-billing-tips-and-best-practices) ·
  [per-code page (98977)](https://www.limberhealth.com/blog/rtm-cpt-code-98977). No RPM
  claims.
- **FDA status:** **no 510(k) and no registration/listing found** (FDA 510(k) and
  registration/listing databases searched 2026-07-14 via the openFDA mirror; the only
  "Limber" registrant is an unrelated prosthetics manufacturer). Limber's own FAQ
  acknowledges the RTM device must "meet the definition of a medical device, as defined by
  the FDA" but discloses no posture of its own — the §201(h) burden is left with the
  billing provider.
- **Billing model:** provider bills; Limber sells SaaS to practices plus value-based
  payer arrangements. Pricing unpublished.

### 2.2 Exer AI (Exer Labs — Exer Scan / Exer Health)

- **What it does:** camera-only computer-vision movement analysis on ordinary
  phones/tablets — MSK and motion-disorder use (orthopedics, gait, tremor, fall risk). No
  wearables. [exer.ai/product/scan](https://www.exer.ai/product/scan)
- **Data captured:** CV joint-angle/ROM measurements ("comparable to traditional
  goniometry"), longitudinal motion data, plus patient self-reported inputs for RTM.
- **Codes billed — BILLING-VERIFIED:** the vendor's RTM product page lists **98975
  (~$24), 98977 (~$69/30 days), 98980 (~$61), 98981 (~$49)** with a rates-vary caveat.
  [exer.ai/product/rtm](https://www.exer.ai/product/rtm). No RPM claims.
- **FDA status:** **registered/listed only, NOT cleared — and under an active FDA Warning
  Letter.** Exer Labs (registration/FEI 3020929899) lists "Exer Health" (product code QKC)
  and "Exer Scan" (product code ISD), both Class II **510(k)-exempt** under 21 CFR
  890.5360 ([openFDA listing query](https://api.fda.gov/device/registrationlisting.json?search=registration.owner_operator.firm_name:%22exer%22));
  no 510(k) exists. FDA's **Warning Letter of 2025-02-10** found Exer Scan **adulterated
  and misbranded**: marketing it for AI-based *screening/diagnosis* (Parkinson's, cerebral
  palsy, fall-risk) "exceed[s] the limitations on exemption" at 21 CFR 890.9(a) and would
  require a 510(k)/PMA Exer does not have.
  [FDA Warning Letter](https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/warning-letters/exer-labs-inc-699218-02102025).
  No close-out or subsequent clearance found as of 2026-07-14.
- **Billing model:** provider bills; B2B SaaS with billing-integration APIs. Platform
  pricing unpublished.

### 2.3 OneStep (Celloscope Ltd.)

- **What it does:** smartphone-IMU gait and mobility analysis (no wearable, no
  calibration) for PT/rehab, senior living, and health systems — passive background gait
  monitoring during daily life plus active functional tests, HEP, PROs, care messaging,
  and built-in **RTM billing management**. This is the closest *functional* analog to our
  BioMech gait/balance stream. [onestep.co/product](https://www.onestep.co/product)
- **Data captured:** 30+ gait parameters (gait speed, stride length, cadence,
  double-support, symmetry, variability), 15+ functional tests, fall-risk signals, PROs,
  passive daily-life data ("28 days of meaningful data every month").
- **Codes billed — BILLING-VERIFIED:** vendor RTM page documents **98975 (~$19.38), 98977
  (16-of-30 days, ~$55.72), 98980 (~$50.18), 98981 (~$40.83)**; a 2026 vendor blog adds
  **98985** and **98979**.
  [onestep.co/solutions/remote-therapeutic-monitoring](https://onestep.co/solutions/remote-therapeutic-monitoring).
  Vendor-published economics: "**$112–$114 average RTM reimbursement per patient per
  month** for OneStep clients" (same page — vendor claim, not payer data). No RPM claims.
- **FDA status:** **FDA-listed, NOT cleared** — and OneStep's own wording is correctly
  "FDA-listed medical device." Manufacturer Celloscope Ltd. (registration/FEI 3021907566)
  is listed under product code **ISD** ("Exerciser, Measuring," Class II, 510(k)-exempt,
  21 CFR 890.5360; listing proprietary name "ExactStep" — an apparent earlier brand)
  ([openFDA listing query](https://api.fda.gov/device/registrationlisting.json?search=registration.owner_operator.firm_name:%22celloscope%22));
  no 510(k) exists.
- **Billing model:** provider bills; OneStep supplies time-tracking and "audit-ready
  documentation." Platform pricing unpublished.

## 3. Sensor-plus-service MSK: Plethy (Recupe)

- **What it does:** connected MSK recovery combining a Bluetooth IMU wearable ("Recovery
  Dot," worn during exercise; joint ROM + rep counts), a bilingual patient app, a
  clinician dashboard, and **Plethy-employed human "Recupe Coaches"** who check in with
  patients — sold into workers' compensation and to medical groups/health systems/PT
  clinics. [plethy.com/what-is-recupe](https://www.plethy.com/what-is-recupe/)
- **Data captured:** sensor-derived ROM and rep counts, engagement/adherence, pain and
  patient-reported progress via app + coach.
- **Codes billed — BILLING-UNVERIFIED:** the site says only, generically, that "Recupe
  supports RPM and RTM billing, RVUs and VBC models"
  ([plethy.com/medical-groups-health-systems](https://plethy.com/medical-groups-health-systems/));
  **no Plethy page lists specific CPT codes**, and the vendor's own study title even calls
  the product "Remote Patient Monitoring," blurring RPM/RTM. Given the ISD-listed MSK
  sensor, the 98977 family would be the plausible pathway — but that is inference, not
  vendor documentation.
- **FDA status:** **registered/listed only, NOT cleared.** Plethy (registration/FEI
  3015099260) lists "Recupe" under **ISD** (Class II, 510(k)-exempt) and **KQW**
  (nonpowered goniometer, Class I exempt)
  ([openFDA listing query](https://api.fda.gov/device/registrationlisting.json?search=registration.owner_operator.firm_name:%22plethy%22));
  no 510(k).
- **Billing model:** two-sided — employer/payer-funded episodes in workers' comp;
  provider-bills in the clinical channel. Pricing unpublished.

## 4. The company-bills digital MSK clinics: Hinge Health and Sword Health

The two biggest names in "reimbursed MSK digital health" are **not** RTM code stories at
all — a finding that matters for us.

### 4.1 Hinge Health

- **What it does:** digital MSK clinic sold as a covered benefit — app-based exercise
  therapy with a remote care team (PTs, physicians, coaches), **TrueMotion**
  computer-vision motion tracking ("100+ reference points"), and the optional **Enso**
  wearable neurostimulation device.
  [hingehealth.com](https://www.hingehealth.com/) ·
  [motion tech](https://www.hingehealth.com/product/precision-motion-technology/) ·
  [Enso](https://www.hingehealth.com/product/enso/)
- **Data captured:** CV kinematics, engagement, PROs/outcomes.
- **Codes billed — BILLING-UNVERIFIED for RTM/RPM:** no Hinge billing guide or CPT sheet
  exists; its **S-1** (NYSE IPO, May 2025) describes contracting with employers and
  health plans ("we partner with clients' health plans, TPAs, PBMs … [for] billing") and
  never mentions RTM CPT codes
  ([S-1 filing](https://www.sec.gov/Archives/edgar/data/1673743/000119312525051004/d829170ds1.htm)).
  The member help center confirms the flow: members get an EOB, owe $0, "your employer or
  benefit plan covers the cost"
  ([help.hingehealth.com](https://help.hingehealth.com/en/support/solutions/articles/155000005013-how-does-billing-work-)).
  **Hinge is the biller under its own contracts — a clinical-services company, not a
  provider-enabler.**
- **FDA status:** the **hardware is genuinely 510(k)-cleared** — **K233784** (ENSO Model
  2, cleared 2024-02-23, product code NUH) and **K254216** (Enso for Migraine, cleared
  2026-04-16, product code PCC), both confirmed in FDA's 510(k) database
  ([K233784 letter](https://www.accessdata.fda.gov/cdrh_docs/pdf23/K233784.pdf) ·
  [K254216 letter](https://www.accessdata.fda.gov/cdrh_docs/pdf25/K254216.pdf)).
  The motion-tracking **software has no clearance or listing found** — claims-only.
  UNVERIFIED: a 510(k) number for the original pre-2024 Enso.
- **Billing model:** company bills employers/plans directly; per-participant fees
  (secondary analysts report roughly $600–1,000/participant/year — UNVERIFIED against
  vendor disclosure).

### 4.2 Sword Health

- **What it does:** virtual MSK/pain care pairing licensed Doctors of Physical Therapy
  with "Phoenix," an AI care agent, plus home-shipped hardware (Thrive Pad tablet with
  computer-vision cameras; Move wearable; Bloom pelvic device).
  [swordhealth.com](https://swordhealth.com/) ·
  [Thrive Pad](https://swordhealth.com/articles/meet-thrive-pad-recovery-just-got-smarter)
- **Data captured:** CV kinematics (form, reps, ROM), wearable activity, pelvic-sensor
  data, PROs (PGIC is the contractual outcome metric).
- **Codes billed — BILLING-UNVERIFIED for RTM/RPM:** no Sword CPT documentation exists.
  Verified mechanics are **outcome-priced B2B contracts**: 50% of the fee on member
  activation, 50% on clinically meaningful improvement, capped at $1,000/member
  ([swordhealth.com/value/fair-pricing](https://swordhealth.com/value/fair-pricing)).
  (Sword does direct-bill private insurers in **Canada** as physiotherapy — not US CPT
  billing.)
- **FDA status:** **registered/listed only; NOT cleared.** Sword entities list "Digital
  Therapist"/"Sword Thrive" under **ISD** and Bloom devices under **KXQ**, both Class II
  510(k)-exempt
  ([openFDA listing query](https://api.fda.gov/device/registrationlisting.json?search=registration.owner_operator.firm_name:%22sword%20health%22));
  a 510(k) search returns nothing. Caution: Sword marketing has used "FDA certifications"
  ([2020 press release](https://www.prnewswire.com/news-releases/sword-health-becomes-the-only-digital-musculoskeletal-care-provider-with-hitrust-soc-2-and-fda-certifications-301111868.html)) —
  the accurate characterization is registered/listed.
- **Billing model:** company bills employers/health plans (PMPM/per-episode/outcome
  fees); claims Medicare Advantage savings via plan partnerships.

## 5. The balance-testing analog: Sway Medical

The closest technical comparable to our balance/gait stream — and it took a different
road on both regulation and reimbursement.

- **What it does:** smartphone-accelerometer **balance and cognitive testing** SaMD used
  by athletic trainers and clinicians (concussion/fall-risk workflows). Acquired by
  Healthy Roster, announced 2025-10-31
  ([swaymedical.com announcement](https://www.swaymedical.com/articles/healthy-roster-acquires-sway-medical)).
- **Data captured:** postural-sway balance scores from the phone's built-in
  accelerometer (held to the chest), plus reaction-time/cognitive test batteries and
  remote test scheduling.
- **Codes billed — BILLING-VERIFIED, but NOT RTM/RPM:** Sway's own billing documentation
  lists neurobehavioral/neuropsychological and functional testing codes — **96116,
  96130–96139, 96146, 97530, 97750**
  ([docsv1.swaymedical.com billing codes](https://docsv1.swaymedical.com/overview/billing/billing-codes.html)).
  **No RTM or RPM codes are documented despite the product's remote-testing capability**
  — the closest balance-app comparable monetizes via *point-in-time testing* codes, not
  recurring monitoring codes.
- **FDA status:** **genuinely 510(k)-CLEARED, twice** — **K121590** ("Sway Balance,"
  cleared 2012-09-20 under Sway's founding entity Capacity Sports, LLC: a *software-only*
  smartphone-accelerometer balance-assessment device, product code LXV) and **K241737**
  ("Sway System Sports Plus," cleared 2025-02-15, Class II, product code POM)
  ([K121590 510(k) summary](https://www.accessdata.fda.gov/cdrh_docs/pdf12/K121590.pdf) ·
  [K241737](https://www.accessdata.fda.gov/cdrh_docs/pdf24/K241737.pdf)).
  K121590 is the single most relevant regulatory precedent in this document: FDA cleared
  a phone-sensor balance app as a medical device 14 years ago.
- **Billing model:** provider bills; SaaS subscription, per-patient pricing unpublished.

## 6. General RPM/care-management enablement platforms

Included to benchmark the "enablement platform" archetype we'd compete with on evidence
tooling — both are RPM-first, neither documents RTM.

### 6.1 Optimize Health → Vivo Care

- **What it does:** RPM + CCM **services-plus-platform** — connected vitals devices,
  dashboards, and **US nurse-led clinical monitoring delivered as "an extension of your
  staff"** (the vendor supplies the monitoring labor that accrues billable minutes).
  Rebranded Vivo Care in 2025; optimize.health now redirects to
  [vivocaresolutions.com](https://vivocaresolutions.com/).
- **Data captured:** device vitals (BP, glucose, weight, SpO2), care-plan goals,
  encounter/time tracking.
- **Codes billed — BILLING-VERIFIED (RPM/CCM, not RTM):** vendor blog documentation of
  **99453** (setup, ~$19.65) and the RPM family 99454/99457/99458, plus CCM 99490/99439
  ([vendor 99453 guide](https://vivocaresolutions.com/blog/a-top-blog-rewrite-definitive-guide-to-cpt-code-99453/)).
  **No RTM.**
- **FDA status:** no clearance or registration/listing found for the platform itself
  (UNVERIFIED-NEGATIVE; it orchestrates third-party FDA-regulated vitals devices).
- **Billing model:** provider bills; vendor sells platform + staffing. Pricing
  unpublished.

### 6.2 Carium

- **What it does:** care-management/RPM enablement software (no hardware) — patient app,
  clinician dashboards, pathways ([carium.com](https://carium.com/)).
- **Codes billed — BILLING-PARTIALLY-VERIFIED (historical):** a vendor FAQ distributed
  via Henry Schein (~2021) documents RPM **99453 ($21), 99454 ($69/30 days), 99457
  ($54/mo), 99458 ($42/mo)** and combining with CCM 99490/99487
  ([Carium FAQs PDF](https://www.henryscheinsolutionshub.com/wp-content/uploads/2021/03/Carium-FAQs.pdf)) —
  but the current site has no public CPT page and those rates predate CY2026. **No RTM.**
- **FDA status:** no clearance or registration/listing found (UNVERIFIED-NEGATIVE).
- **Billing model:** provider bills; SaaS.

## 7. Comparison vs. our app

Our column is stated from this repo's decision records (ADR-0003/0006/0007/0014/0016;
[`reimbursement-analysis.md`](reimbursement-analysis.md) §1) — it is a **plan-of-record
description, not a claim of billability**. Note the recorded owner decision (2026-07-14):
BioMech's own device/assessment billing is **separate and outside our enablement scope**;
our scope is the app-captured streams (ADL self-report, imported BioMech report data, EMR
labs) — see [`reimbursement-signoff-packet.md`](reimbursement-signoff-packet.md) §2.4.

| Product | Data streams | Objective device stream? | RTM code fit | FDA status | Enabler vs biller | Patient + clinician surfaces |
|---|---|---|---|---|---|---|
| **Our app** | **BioMech balance/gait + ADL self-report + EMR labs (SMART on FHIR)** — multi-stream, provenance-complete, non-diagnostic | **Indirect**: BioMech's device data via PDF import (`document_imported`); direct `device_measured` API path deferred | 98977 family **candidate — PENDING professional validation** (analysis §2) | **UNDETERMINED — the open question** (sign-off packet §4) | **Enabler** (clinic bills; app exports evidence) | Both: patient app (web + Android) + consent-gated clinician panel |
| Limber Health | HEP adherence + pain + PROs | No (self-report software only) | **Billing-verified**: 98975/77/80/81 + 98985/79 | None found | Enabler | Both |
| Exer AI | CV joint angles/ROM + self-report | Yes (camera CV, own software) | **Billing-verified**: 98975/77/80/81 | Registered/listed (QKC, ISD); **active FDA Warning Letter** | Enabler | Both |
| OneStep | 30+ smartphone-IMU gait params + PROs, passive daily monitoring | Yes (phone IMU, own software) | **Billing-verified**: 98975/77/80/81 + 98985/79 | FDA-listed (ISD) | Enabler | Both |
| Plethy Recupe | Wearable IMU ROM/reps + PROs + coach notes | Yes (own sensor) | **Unverified** (generic "RPM and RTM billing") | Registered/listed (ISD, KQW) | Enabler + coach service; employer-funded in workers' comp | Both |
| Hinge Health | CV kinematics + PROs; Enso neurostim | Yes (own CV + cleared device) | **Unverified — bills B2B contracts, not RTM codes** | Hardware 510(k)-**cleared** (K233784, K254216); software none | **Biller** (company contracts) | Patient-first; internal care team |
| Sword Health | CV kinematics (Thrive Pad) + wearable + PROs | Yes (own hardware) | **Unverified — outcome-priced B2B contracts** | Registered/listed (ISD, KXQ); no 510(k) | **Biller** (company contracts) | Patient-first; internal PT team |
| Sway Medical | Phone-accelerometer balance + cognitive tests | Yes (cleared phone-sensor SaMD) | **None — bills testing codes** 96116/96130–39/96146/97530/97750 | 510(k)-**cleared** (K121590, K241737) | Enabler | Clinician-administered focus |
| Optimize/Vivo Care | Third-party vitals devices + time tracking | Via third-party devices | None (RPM 99453–58 + CCM, billing-verified) | None found | Enabler + staffing service | Both |
| Carium | Configurable RPM/care pathways | Via third-party devices | None (RPM/CCM, historical vendor doc) | None found | Enabler | Both |

## 8. What the reimbursed products have that we lack (blunt)

1. **A clinical service attached to the software.** RTM/RPM dollars are paid for
   *clinician work* (monitoring days, management minutes, live communication). Hinge and
   Sword employ the PTs; Plethy supplies human coaches; Optimize/Vivo rents out nurses.
   We ship software only — every billable minute must come from our clinic customers'
   own staff, and our tooling for capturing those minutes **does not exist yet**
   (sign-off packet §2.2).
2. **A resolved FDA posture.** Every billing-verified RTM product with an objective data
   stream holds at least a 510(k)-exempt FDA registration/listing for its own
   software/sensor (Exer, OneStep, Plethy — all ISD-family), and the genuinely cleared
   ones (Sway, Hinge's Enso) prove the full path is walkable. Our status is
   **UNDETERMINED**, and our objective stream's device character belongs to BioMech, not
   us. (Limber is the counterexample — billing-verified RTM with no FDA footprint of its
   own — which shows the burden can sit with the billing provider, but Exer's Warning
   Letter shows what happens when software oversteps the exemption.)
3. **An owned, end-to-end objective measurement stream.** Exer/OneStep/Sword/Hinge
   *measure* with their own camera/IMU pipelines and get device-grade provenance natively.
   Our V1 objective stream is a **parsed PDF of someone else's device output**
   (`document_imported`) — evidentially weaker until the deferred BioMech API/SDK path
   lands (analysis §7 item 6).
4. **Shipping RTM operations tooling.** Day counters, time tracking, audit-ready billing
   reports, EHR/billing integrations — the things OneStep and Limber sell *today* are
   precisely our unbuilt Wave 4 backlog. We are behind the category, not ahead of it.
5. **Published billing playbooks and economics** (OneStep's "$112/patient/month," Limber's
   per-code rate pages) that de-risk the purchase decision for a clinic. We have nothing
   equivalent — and can't honestly publish one until sign-off.

## 9. What we have that they lack

1. **Multi-stream fusion.** Every MSK product above is single-modality (motion or
   self-report) plus PROs. Nobody reviewed fuses **objective balance/gait + structured ADL
   self-report + EMR-pulled labs** into one longitudinal, provenance-complete record with
   an explainable trajectory over all three (ADR-0003's invention thesis).
2. **Patient-held consent and a research-grade store.** ALCOA+/Part-11-aligned immutable
   observations, per-datum provenance, and a patient-controlled `share_with_clinic` gate
   (ADR-0006/0012/0020) — audit-defensible evidence *by construction*, which is exactly
   what RTM audits demand (operations §HOW-4) and none of the vendors advertises at this
   depth.
3. **Explainability and an honest non-diagnostic line.** A deterministic
   direction/confidence/signals engine (no black-box scoring), with AI used only as an
   off-by-default rephrasing layer — a posture that both differentiates clinically and is
   the thing that keeps software on the right side of the exemption line Exer crossed.
4. **EMR integration as a first-class stream** (SMART on FHIR pull) and **payer-agnostic
   fact capture** (analysis §6) rather than hard-coded Medicare code numbers.

## 10. The three load-bearing implications for our Wave 4 build

1. **The FDA determination is the gate, and the market shows the expected answer-shape.**
   Billing-verified RTM products with objective streams carry at least an FDA
   registration/listing for their own software; Exer's Warning Letter marks the ceiling
   (no diagnostic/screening claims under a 510(k)-exempt listing); Sway's K121590 proves a
   phone-sensor balance app can be a cleared device outright. Wave 4 must not start ahead
   of the sign-off packet's §4 determination — and the likely outcomes are either "ride on
   BioMech's device status" or "adopt a deliberate listed-device posture for our software."
   Our non-diagnostic discipline (ADR-0003/0016) is an asset in either outcome.
   **Owner decision 2026-07-14 ("BioMech is billed separately as for now" — sign-off
   packet §2.4) sharpens this:** since BioMech's device/assessment billing sits outside
   our enablement scope, our nearest structural comparables are the **software-led RTM
   products** — Limber's software-only enabler posture and the OneStep/Exer
   app-as-listed-device (SaMD) posture — **not** the device-plus-software bundles
   (Plethy, Sword, Hinge). The primary FDA question for our scope is therefore our own
   software's §201(h)/SaMD status.
2. **Our enabler-not-biller posture matches the archetype that actually bills RTM — so the
   evidence tooling IS the product.** The winners in the provider-enabler lane compete on
   audit-ready evidence: days-with-data counters, time ledgers, billing-ready exports.
   That is precisely analysis §7 items 1/2/5 — build them as the core Wave 4 deliverable,
   parameterized for the 2026 two-tier windows (2–15 / 16–30) the vendors are already
   documenting (98985/98979).
3. **Monetization model is a choice, not a consequence of the data — keep capture
   payer-agnostic.** The closest technical analog (Sway) monetizes identical data through
   point-in-time testing codes rather than RTM; the biggest MSK players bypass CPT
   entirely via B2B contracts. Recording generic billable *facts* (days, minutes,
   communications, consent, provenance) rather than code numbers — already the analysis
   §6/§7 rule — preserves every one of these roads (RTM now; testing codes or
   employer/plan contracts later) without rework.

---

> ## ⚠️ CAVEAT (bottom — same weight as the top)
>
> **Decision-support market research only — NOT billing, coding, or legal advice**; nothing
> here authorizes anyone to bill any payer. Vendor claims, codes, and rates change; every
> third-party fact above is as-published on 2026-07-14 at the cited URL, and every
> "BILLING-VERIFIED" label means only "the vendor documents these codes," not "claims were
> paid or compliant." Verify against primary sources (CMS rule, FDA databases, the vendor's
> current pages) before relying on anything here.

## Sources

All accessed 2026-07-14. FDA facts verified against FDA's 510(k) and Establishment
Registration & Device Listing databases (accessdata.fda.gov, via the openFDA API mirror
api.fda.gov). Note: swordhealth.com was rate-limiting automated access (HTTP 429) at
final link-check time; its pages were content-verified the same day.

- Limber Health: <https://www.limberhealth.com/frequently-asked-questions> · <https://www.limberhealth.com/blog/remote-therapeutic-monitoring-billing-tips-and-best-practices> · <https://www.limberhealth.com/blog/rtm-cpt-code-98977>
- Exer AI: <https://www.exer.ai/product/rtm> · <https://www.exer.ai/product/scan> · <https://api.fda.gov/device/registrationlisting.json?search=registration.owner_operator.firm_name:%22exer%22> · <https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/warning-letters/exer-labs-inc-699218-02102025>
- OneStep: <https://onestep.co/solutions/remote-therapeutic-monitoring> · <https://www.onestep.co/product> · <https://api.fda.gov/device/registrationlisting.json?search=registration.owner_operator.firm_name:%22celloscope%22>
- Plethy: <https://www.plethy.com/what-is-recupe/> · <https://plethy.com/medical-groups-health-systems/> · <https://api.fda.gov/device/registrationlisting.json?search=registration.owner_operator.firm_name:%22plethy%22>
- Hinge Health: <https://www.hingehealth.com/> · <https://www.hingehealth.com/product/enso/> · <https://www.hingehealth.com/product/precision-motion-technology/> · <https://help.hingehealth.com/en/support/solutions/articles/155000005013-how-does-billing-work-> · <https://www.sec.gov/Archives/edgar/data/1673743/000119312525051004/d829170ds1.htm> · <https://www.accessdata.fda.gov/cdrh_docs/pdf23/K233784.pdf> · <https://www.accessdata.fda.gov/cdrh_docs/pdf25/K254216.pdf>
- Sword Health: <https://swordhealth.com/> · <https://swordhealth.com/articles/meet-thrive-pad-recovery-just-got-smarter> · <https://swordhealth.com/value/fair-pricing> · <https://api.fda.gov/device/registrationlisting.json?search=registration.owner_operator.firm_name:%22sword%20health%22> · <https://www.prnewswire.com/news-releases/sword-health-becomes-the-only-digital-musculoskeletal-care-provider-with-hitrust-soc-2-and-fda-certifications-301111868.html>
- Sway Medical: <https://docsv1.swaymedical.com/overview/billing/billing-codes.html> · <https://www.accessdata.fda.gov/cdrh_docs/pdf12/K121590.pdf> · <https://www.accessdata.fda.gov/cdrh_docs/pdf24/K241737.pdf> · <https://www.swaymedical.com/articles/healthy-roster-acquires-sway-medical> · <https://www.swaymedical.com/>
- Optimize Health / Vivo Care: <https://vivocaresolutions.com/> · <https://vivocaresolutions.com/blog/a-top-blog-rewrite-definitive-guide-to-cpt-code-99453/>
- Carium: <https://carium.com/> · <https://www.henryscheinsolutionshub.com/wp-content/uploads/2021/03/Carium-FAQs.pdf>
- Code-family baselines: CMS Remote Patient Monitoring page <https://www.cms.gov/medicare/coverage/telehealth/remote-patient-monitoring> · CY2026 PFS final rule <https://www.federalregister.gov/documents/2025/11/05/2025-19787/medicare-and-medicaid-programs-cy-2026-payment-policies-under-the-physician-fee-schedule-and-other>
