# Brainstorm #2 — V1 Product Definition (all lenses)

**Date:** 2026-07-11
**Input:** `docs/requirements/2026-07-11-product-requirements-v1.md` (owner-stated)
**Protocol:** CLAUDE.md §6 — every canonical lens applied, plus topic-specific lenses.
**Builds on:** Brainstorm #1 (2026-07-11) — general product space. This one is scoped
to the stated requirements: patient-fronting app; B2C + clinical versions; biometrics;
neuropathy-specific features; BioMech data recordings (V1 PDF → V2 API/SDK); full
feature toggling (user-side in B2C, clinician-side in clinical).

---

## The core architectural insight up front

The requirements describe **one product with two authority models**, not two apps:

- Every feature is a **capability** in a registry. Each capability has an
  **availability** state (is it offered at all?) and an **activation** state (is it
  on for this patient?).
- **B2C:** availability controlled by us/ops; activation controlled by the patient.
- **Clinical:** availability controlled by clinic-level defaults; activation
  controlled by the **clinician per patient**; data routes to the prescribing clinic.
- Same codebase, same backend, same capability registry — different **toggle
  authority** and different **data-routing policy**.

> **INVENTION CANDIDATE** — *Clinician-prescribed remote configuration of at-home
> digital neuropathy assessments*: the clinician toggles on a specific measurement
> (e.g. balance test), sets frequency/parameters, the patient app reconfigures itself,
> runs the protocol, and returns results to the clinic as a structured recording.
> Effectively a "digital assessment prescription." Combined with the measurement
> methods from Brainstorm #1, this is the strongest system-level claim surface so far.

---

## 1. Physician lens

- The clinician toggle panel is a **prescription surface**: enabling "vibration
  self-test, 2×/week" is an order. It needs an order-like audit trail: who enabled
  what, when, for which patient, with what parameters.
- Clinicians will NOT log into another portal to flip switches without payoff. The
  payoff loop: toggle on → patient data flows in → concise review screen → RTM
  billing evidence. Toggle UX must live inside that loop, not beside it.
- Sensible clinical presets beat raw toggles: "DPN monitoring bundle," "CIPN bundle,"
  "post-op bundle" — one click enabling a curated set, individually adjustable after.
- The V1 PDF is the clinical hand-off artifact: one-page summary first (trend arrows,
  flags), detail pages after. Clinicians read the first page only.

## 2. Patient lens

- **B2C toggles are a feature, not a burden**: neuropathy patients are heterogeneous
  (a CIPN survivor doesn't need diabetic foot checks). Frame toggles as "build your
  app" onboarding — pick concerns, the app assembles itself. Everything off = a
  clean, quiet app; that's a legitimate configuration.
- **In the clinical version, patients need transparency**: show "Dr. ___ turned on
  Balance Testing (2×/week)" in an activity feed. Silent remote reconfiguration of a
  health app feels like surveillance; visible prescription feels like care.
- A patient must always retain a **participation veto** (pause sharing / decline a
  test) even when the clinician holds the toggles — consent is not a toggle the
  clinician owns (see HIPAA/Legal).
- Biometrics passively collected (steps, sleep, HR) must be visibly valuable to the
  patient ("your flare days follow short-sleep nights"), not just siphoned to the PDF.

## 3. BioMech Health lens (client/licensee)

- Their stated need is the **data product**: biomech recordings delivered as PDF in
  V1, API/SDK in V2. Design the recording as a **structured session object** from day
  one (device model, calibration state, protocol version, raw-derived metrics,
  quality flags); the PDF is merely renderer #1, the API is renderer #2. No schema
  rework between V1 and V2.
- Embed the machine-readable session JSON **inside** the V1 PDF (PDF/A-3 attachment):
  every PDF ever delivered is retroactively parseable when V2 arrives — no data
  stranded in V1 documents.
- V2 "API or SDK" decision sketch (future ADR): **API** if BioMech Health pulls data
  into their systems; **SDK** if they want our measurement engines inside *their*
  apps. The SDK path licenses the crown-jewel IP — scope it deliberately in the
  license agreement, and keep the measurement core a separate internal module now so
  an SDK cut is possible without surgery later.
- Their requirements arrived through the owner; log any direct BioMech Health
  documents under `docs/requirements/biomech-health/` per CLAUDE.md.

## 4. Apple developer lens

- Server-driven feature flags for shipped features are App-Store-legal (Guideline
  2.3.1 targets hidden/downloaded functionality, not config-gated built-in features).
  All capabilities ship in the binary; toggles gate exposure.
- Biometric auth: Face ID / Touch ID via LocalAuthentication — table stakes for a
  health app, and the "biometrics" requirement's security half.
- Physiological biometrics: HealthKit read scopes requested **per capability at
  activation time**, not all at first launch — toggling a feature on is the natural
  consent moment (better review optics, better trust).
- Remote clinician-triggered config changes arrive via silent push + pull-on-open;
  the app must behave correctly offline with the last-known toggle state.

## 5. Android developer lens

- Same capability registry; BiometricPrompt for auth; Health Connect permissions are
  granted per data type, which maps cleanly onto per-capability activation.
- Haptic-based measurements (vibration test) stay iOS-first per Brainstorm #1;
  the capability registry makes this clean — that capability is simply *unavailable*
  on unsupported hardware, and availability-by-hardware is a first-class registry
  concept (not an error state).
- PDF rendering does NOT happen on-device (fragmentation, fonts, consistency) —
  server-side generation, both platforms just view/share the result.

## 6. HIPAA / privacy lens

- The two versions have **different legal characters**: B2C ≈ FTC Health Breach Rule
  + state laws; clinical = we are a **business associate of each clinic** → BAA per
  clinic, HIPAA fully applies to that data flow. Same backend, so build everything to
  the HIPAA standard (already our rule) with **per-clinic tenant isolation**.
- Transmitting data to a clinic requires **patient authorization/consent captured in-
  app, revocable, with an audit trail**. Toggle-on by a clinician must not be able to
  start data flow before patient consent exists for that flow.
- **Toggle events are themselves audit-relevant records** (who configured a patient's
  monitoring): log them like PHI access.
- PDFs are PHI at rest: encrypted storage, expiring signed links (no email
  attachments of PHI), delivery only to authenticated clinic endpoints.

## 7. SOC 2 / security lens

- The toggle system is an **authorization system** — treat it like one: server-side
  enforcement (client toggles are UI hints, the API enforces), role-based authority
  (patient vs clinician vs clinic-admin vs ops), immutable toggle-event log.
- Feature-flag tooling choice matters: PHI-adjacent assignments (patient ↔ enabled
  capabilities) stay in **our** database; a third-party flag service may only ever
  hold anonymous, non-patient-scoped kill switches.
- PDF pipeline is an attack surface (server-side rendering of user-influenced data):
  sandbox the renderer, treat all patient text as untrusted input, sign generated
  PDFs so clinics can verify integrity/provenance.

## 8. Marketing lens

- Two-version story is clean: **"Your nerve health, your way"** (B2C, you choose
  your features) and **"Prescribed by your clinic"** (clinical, your care team
  configures it). The configurability itself is marketable in both directions.
- B2C toggles enable segment-specific storefronts later (a "CIPN edition" is just a
  preset), without forking the product.
- Disclosure discipline still applies: market *what it does for you*, not *how the
  measurements work*, until filings are done.

## 9. Legal & regulatory lens

- The FDA wellness/device line from Brainstorm #1 now gets a twist: **in the clinical
  version, a clinician prescribing app-based monitoring pushes the product toward
  "intended for use in the diagnosis/monitoring of disease."** Counsel must review
  the clinical version's claims and workflow specifically — it is closer to the
  device line than the identical features in B2C dress.
- Clinician toggle actions may constitute part of the medical record → retention
  obligations for toggle/audit logs align with medical-record retention, not app-log
  retention.
- The license to BioMech Health must anticipate V2: API access vs SDK embedding are
  very different license scopes (SDK = their apps ship our methods). Flag now, draft
  once.
- PDF reports delivered to clinics should carry versioned disclaimers and the
  protocol/algorithm version used — defensibility and reproducibility.

## 10. Accessibility lens

- A toggle-dense settings UI is an accessibility trap: group by concern, plain-
  language names ("Balance check-ins," not "Postural sway module"), one-line "what
  you get / what's collected" per toggle, fully screen-reader navigable.
- The "build your app" onboarding must work voice-first and with large targets —
  same numb-fingertip constraints as everything else (Brainstorm #1 stands).
- Clinical-version transparency feed doubles as an accessibility win: one place to
  hear "what changed on my app and why."

## 11. Payer / reimbursement lens

- Clinician-configured monitoring + data transmitted to the clinic **is the RTM
  billing shape** (CPT 98975–98981): device supply, data transmission ≥16 days/30,
  clinician review time. The toggle/audit system should count transmission-days and
  review interactions per patient natively — this is the clinic version's ROI story.
- The V1 PDF should include a payer-friendly monitoring summary (days transmitted,
  assessments completed) so clinics can substantiate billing from the artifact they
  already receive.

## 12. Data science / ML lens

- Toggles create **structured missingness**: analytics must always condition on
  "capability active" windows, or every insight is biased. The event schema needs
  first-class `capability_state` context on every datum from migration #1.
- Toggle configurations across the fleet are themselves valuable data: which bundles
  do clinicians actually prescribe, which toggles do B2C users enable/abandon —
  product analytics with no PHI needed.
- Biometrics fusion (sleep/HR/steps × symptoms) remains the insight engine; in the
  clinical version those insights can surface to the clinician review screen too.

## 13. Clinical research / validation lens

- The clinical version is a **built-in study platform**: clinician-prescribed
  protocols + structured recordings + consent framework ≈ decentralized-trial
  infrastructure. The validation study for the measurement features (Brainstorm #1)
  can run *on* the clinical version with a research flag — same pipes.
- Protocol versioning in every recording (already needed for PDFs) is exactly what
  reproducible research requires. One design, three payoffs (clinic, FDA, papers).

## 14. Caregiver / family lens

- In B2C, "caregiver view" is just another toggleable capability with its own consent
  gate. In clinical, caregiver access may need clinician awareness too.
- Caregiver notifications ("foot check missed 3 days") must respect the same
  no-PHI-in-push rule.

## 15. Agile lens

- Sequencing (per requirements): **B2C patient app first**, clinical second — but the
  capability registry, consent, and audit foundations are shared and come first.
- Proposed slicing:
  - **Sprint block A (foundation):** capability registry + toggle service (server-
    enforced), auth incl. biometric unlock, consent framework, audit log, event
    schema. No visible features yet — this is the chassis.
  - **Sprint block B (B2C MVP):** neuropathy feature set v1 (symptom/flare logging,
    body map, meds/titration, foot-photo log, education), biometrics ingestion
    (HealthKit first), insights v1, "build your app" onboarding with user toggles.
  - **Sprint block C (recordings + PDF):** biomech recording session object,
    first measurement capability (balance/sway — least hardware-fragile), server-side
    PDF v1 with embedded JSON.
  - **Sprint block D (clinical):** clinic tenancy, clinician web portal with toggle/
    preset panel, patient consent-to-transmit flow, PDF delivery to clinic, RTM
    counters.
- Each block ends with an ADR sweep: decisions made during the block get recorded.

## 16. DevOps lens

- Toggle service = new critical-path infra: server-authoritative flags in our
  Postgres (not a SaaS flag vendor for patient-scoped state), cached client-side,
  delivered via config endpoint + push invalidation. Kill switches for every
  capability (ops-level availability) fall out of the same design.
- PDF generation as an isolated worker service (queue-driven, sandboxed, no inbound
  network), artifacts to encrypted object storage, delivery via expiring signed URLs;
  render templates versioned in-repo.
- Multi-tenancy (clinics) shapes infra early: per-tenant data isolation tests in CI,
  tenant-scoped backups/exports, per-clinic BAA-driven data-retention config.
- The V2 API/SDK future argues for an internal **measurement-core module boundary
  now** (separate package, no app dependencies) — CI enforces the boundary so the
  SDK cut stays possible.

## Topic-specific lens added this round (per CLAUDE.md §6): Support / Operations

- Remote toggling means support tickets like "my app changed overnight": the
  transparency feed (patient-visible change log) is also the support deflection tool.
- Clinic onboarding is an ops workflow (BAA, tenant setup, clinician accounts,
  training) — productize it as a checklist from pilot #1.
- Every capability needs a support-facing "state inspector": what's available/active
  for this user and why (authority, timestamp, actor) — debuggability of the toggle
  system is a launch requirement, not a nice-to-have.

---

## Decisions this brainstorm forces (ADR queue)

1. **Capability registry & toggle authority model** — the chassis; blocks everything.
2. **Platform strategy** — unchanged from Brainstorm #1, now sharpened: iOS-first
   B2C MVP, Android at logging-parity, measurement features iOS-first.
3. **"Biometrics" scope confirmation** — auth + physiological, per requirements doc
   open question.
4. **Recording session schema + PDF/A-3 embedded-JSON format** — the V1→V2 bridge.
5. **Backend stack & tenancy model** — needed before Sprint block A.
6. **Regulatory posture of the clinical version** — counsel review of the
   prescription-like toggle workflow.

## Invention candidates added this round

- Clinician-prescribed remote configuration of at-home digital assessments
  ("digital assessment prescription") — see top of document.
- Capability-scoped consent choreography: toggle-on → consent → permission → data
  flow as a single auditable state machine spanning patient and clinician actors.
- (Carried from Brainstorm #1: haptic VPT self-test; fused fall-risk score; guided
  foot-photo change detection; sensory-deficit-adaptive UI.)
