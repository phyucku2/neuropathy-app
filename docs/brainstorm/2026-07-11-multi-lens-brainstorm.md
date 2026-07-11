# Neuropathy App — Multi-Lens Brainstorm

**Date:** 2026-07-11
**Status:** Brainstorm (not a decision record — decisions graduate to `docs/decisions/` ADRs)
**Clean-room note:** Everything below is derived from first principles and public,
industry-standard knowledge only. No prior-project material was referenced.

---

## 0. Framing

Peripheral neuropathy affects an estimated 2%+ of the general population and up to
half of people with diabetes. Major segments: diabetic peripheral neuropathy (DPN,
largest), chemotherapy-induced (CIPN), idiopathic, autoimmune, and alcohol-related.
Core patient burdens: burning/tingling pain (often worse at night), numbness, sleep
disruption, balance problems and falls, and — for diabetics — foot ulcers and
amputation risk. The condition is chronic, fluctuating, and notoriously poorly
captured in 15-minute clinic visits.

**Working thesis:** the app closes the gap between what patients live with daily and
what clinicians can see, while adding objective, phone-native measurements no paper
diary can capture.

---

## 1. Physician lens (neurology / endocrinology / podiatry / primary care)

What a treating clinician actually wants:

- **Structured longitudinal data, not diaries of noise.** Trends in pain intensity,
  character (burning vs. stabbing vs. numbness), location (distal → proximal spread),
  and night-time severity. A visit-prep summary that reads in 30 seconds.
- **Validated instruments** administered on a schedule (screening and severity scales,
  quality-of-life and pain-quality measures). ⚠️ Many validated scales are copyrighted
  and require licensing — see Legal lens. Selection is an ADR-level decision.
- **Medication response tracking:** titration progress, adherence, side effects, and
  pain response for the common agents (anticonvulsants, SNRIs, TCAs, topicals).
  Titration is where patients abandon therapy; guided titration support is high-value.
- **Red-flag escalation:** rapidly progressive weakness, new foot wound, signs of
  infection → "contact your clinician now" pathways (carefully worded; see Legal).
- **Diabetic foot care:** daily foot-check reminders with a photo log clinicians can
  scan across time.
- **Eventually:** EHR integration via FHIR; but a clean PDF/summary export gets 80%
  of the value first.

## 2. Patient lens

- **Logging must cost almost nothing.** Pain flares happen at 2 a.m.; the log entry
  must take under 10 seconds. One-tap "flare" button, voice entry, smart defaults
  from prior entries.
- **Numb fingertips are the user's baseline.** See Accessibility lens — this is not
  an edge case, it is the primary persona.
- **Insight, not just capture:** "your pain is consistently worse on days after poor
  sleep" beats any chart. Patients want to know *what makes it worse* and *whether
  anything is helping*.
- **Validation and hope:** progression fear (amputation, wheelchair) is constant.
  Progress views should emphasize what's stable/improving, never gamify pain.
- **Practical wants:** medication reminders tied to titration schedules, appointment
  prep ("show my doctor this"), plain-language education, "explain my condition to
  my family" shareables.
- **Night mode literally matters:** symptoms peak at night; dark, low-stimulation UI
  for 2 a.m. logging.

## 3. BioMech / movement-health lens

This is where the phone becomes an instrument rather than a notebook — and where the
patentable surface is likely concentrated.

- **Gait analysis from phone/watch IMU:** cadence, stride-time variability, gait
  asymmetry, walking speed. (Apple already exposes walking steadiness/asymmetry via
  HealthKit — consuming those is table stakes; deriving neuropathy-specific signals
  is the interesting part.)
- **Balance / postural sway testing:** structured stand-still tests (eyes open/closed,
  phone held to chest or in pocket) measuring sway via accelerometer → fall-risk
  trend. > **INVENTION CANDIDATE** — a neuropathy-specific, longitudinal fall-risk
  score fusing sway, gait variability, and self-reported numbness distribution.
- **Vibration perception self-testing via the phone's haptic engine:** psychophysical
  staircase (descending/ascending amplitude, forced-choice response) with the
  fingertip or foot on the device, producing a vibration-perception-threshold proxy
  tracked over time. > **INVENTION CANDIDATE** — including per-device haptic
  calibration and a forced-choice protocol robust to guessing. (Academic prior art
  exists in this space; patent counsel must run a real search — flagged, not assumed.)
- **Foot photo analysis:** guided daily/weekly foot photos with consistent framing;
  later, on-device ML flagging of skin changes/wounds for diabetic users.
  > **INVENTION CANDIDATE** — guided capture + longitudinal change detection tuned
  to neuropathic feet. (Also the most regulated feature here — see Legal.)
- **Autonomic signals:** HRV trends from wearables as an autonomic-neuropathy-adjacent
  signal (research-mode only; never a claim without validation).
- **Sensory mapping:** patient paints numbness/tingling/pain regions on a body/foot
  map over time → objective-ish progression picture clinicians recognize instantly.
  > **INVENTION CANDIDATE** when fused with the instrument-grade measures above into
  a single composite "nerve health" trajectory.

## 4. Apple developer lens

- **Stack:** Swift + SwiftUI. Core Haptics gives fine-grained amplitude control of the
  Taptic Engine (essential for the vibration test); Core Motion for gait/sway;
  HealthKit for walking metrics, steps, sleep; CareKit/ResearchKit are BSD-licensed
  (permitted under our licensing rule) for care plans/surveys/e-consent.
- **App Store health rules:** health data may not be used for advertising or shared
  with data brokers; privacy nutrition labels required; medical-diagnosis claims
  trigger review scrutiny and requests for regulatory evidence. Wellness framing at
  launch keeps review low-risk.
- **Hardware variance:** Taptic Engine output differs across iPhone models —
  vibration testing needs a per-model (or per-device) calibration table. iPhone-only
  first is defensible for measurement fidelity.
- **Watch:** background gait/steadiness collection makes Apple Watch a strong
  companion, not a launch requirement.

## 5. Android developer lens

- **Stack:** Kotlin + Jetpack Compose; Health Connect (successor to Google Fit) for
  steps/sleep/vitals; `VibrationEffect` supports amplitude control (API 26+) but
  **haptic hardware fragmentation is severe** — the vibration test likely needs a
  supported-device allowlist and per-device calibration, or ships later on Android.
- **Play Store:** health apps policy + Data safety section; similar no-ads-on-health-
  data posture.
- **Camera:** CameraX for guided foot photos with consistent exposure/framing.
- **Strategic implication:** sensor/haptic fidelity argues for **iOS-first for the
  measurement features**, with Android at parity for logging/insights/education. This
  is an ADR-level platform decision (options: native ×2, Kotlin Multiplatform shared
  core + native UI, React Native/Flutter + native sensor modules).

## 6. HIPAA lens

- **Threshold question: are we a covered entity/business associate?** A pure
  direct-to-consumer app with no clinician/telehealth involvement is generally *not*
  under HIPAA — it falls under the FTC Health Breach Notification Rule and state
  health-privacy laws (e.g., Washington My Health My Data, California CMIA), some of
  which are stricter than HIPAA in places. The moment we add a clinician portal,
  RTM/RPM billing, or provider partnerships, HIPAA applies.
- **Posture: build to HIPAA standard from day one regardless** (our hard rules already
  require this): encryption in transit and at rest, per-user record isolation, audit
  logging on all health-data reads/writes, role-based least privilege, session
  timeouts, breach-response procedures.
- **Vendors:** only cloud/analytics/crash-reporting vendors that will sign a BAA (or
  that never receive health data). Push notifications must never contain symptom or
  medication content.

## 7. SOC 2 lens

- Start the control habits now, certify later (Type I → Type II once there are
  enterprise/clinic customers — SOC 2 matters for B2B, not B2C).
- **Cheap now, expensive to retrofit:** change management through PRs + branch
  protection (already our rule), MFA/SSO on all infra, least-privilege IAM,
  centralized logging with retention, documented incident-response and backup/restore
  runbooks, vendor risk register, dependency scanning.
- Design the audit-log pipeline once to serve both HIPAA and SOC 2 evidence needs.

## 8. Marketing lens

- **Segments in order of reachability:** (1) diabetic neuropathy — huge, findable via
  podiatrists, endocrinologists, diabetes educators, CGM communities; (2) CIPN — via
  oncology nurses/navigators and cancer-support orgs; (3) idiopathic — via patient
  communities and search ("burning feet at night" class of queries).
- **Positioning:** "see your nerve health" / control and clarity for a condition that
  feels invisible and dismissed. Never cure/reversal claims (FTC substantiation).
- **Business models to test:** B2C freemium (logging free, insights/tests premium);
  B2B2C via podiatry/endocrine clinics (which pairs with RTM billing — see Payer
  lens); pharma partnerships around CIPN much later.
- **⚠️ Disclosure discipline:** marketing may describe generic value ("track symptoms,
  spot patterns") but must NOT publicly describe the novel measurement mechanisms
  before the patent filing strategy is settled (hard rule §3).

## 9. Legal & regulatory lens (incl. FDA)

- **FDA software-as-a-medical-device line is THE product-shaping constraint:**
  - Likely **general wellness / low-risk** (no clearance): symptom + medication
    logging, education, trend visualization, visit-prep reports, reminders.
  - Likely **device territory** (510(k)/De Novo pathways): claiming to *detect or
    diagnose* neuropathy, wound/ulcer detection from photos, fall *prediction*
    (vs. general balance trends), treatment recommendations, red-flag *triage*.
  - **Strategy:** ship the wellness tier commercially; run the measurement features
    (vibration test, sway/gait scores, foot-photo analysis) in a labeled
    research/investigational mode with IRB oversight until counsel/regulatory advisors
    chart the clearance path. This also generates the validation data FDA and payers
    will want.
- **Validated instruments:** several neuropathy/pain/QOL scales require copyright
  licenses; verify per instrument before implementation (ADR + license file).
- **Terms & disclaimers:** "not a substitute for professional medical care";
  red-flag messaging must encourage contacting a clinician without practicing
  medicine; document the wording decisions.
- **Patent:** provisional filing(s) on the invention candidates **before** any public
  beta, App Store listing, or conference demo. Public disclosure kills most non-US
  rights immediately.

## 10. Additional lenses (added per "whomever you can add")

### 10a. Accessibility (arguably the #1 design lens for this app)
- The primary user has **reduced touch sensation**, often reduced vision (diabetic
  retinopathy), and is often 55+. WCAG 2.2 AA minimum; large touch targets (≥ 44 pt),
  high-contrast and dark modes, full VoiceOver/TalkBack support, voice-first logging.
- Haptic feedback is *unreliable feedback* for this population — never use vibration
  as the only confirmation channel.
- > **INVENTION CANDIDATE** — a UI that adapts its touch-target sizes and interaction
  patterns based on the user's own measured sensory deficit. Accessibility as a
  closed loop with the measurement layer.

### 10b. Payer / reimbursement
- **Remote Therapeutic Monitoring (RTM) CPT codes** (98975–98981) reimburse clinicians
  for reviewing patient-reported therapy/adherence data — a natural fit for a
  clinician-facing tier and the strongest near-term B2B revenue logic. RPM codes
  (99453–99458) become relevant if/when physiologic measurement is validated.
- Implication: design the data model so clinician review time and data-transmission
  days are trackable from day one (cheap now, painful to retrofit).

### 10c. Data science / ML
- The killer insight feature is **within-person correlation**: sleep, activity,
  glucose (if shared), meds vs. symptom scores. Requires a clean longitudinal event
  schema from the first migration — every datum timestamped, typed, and source-tagged.
- Prefer on-device inference for anything touching raw sensor streams (privacy story
  + App Store friendliness); server-side only aggregates.
- Every model output shown to users needs an uncertainty/`n`-of-data honesty rule to
  stay on the wellness side of the FDA line.

### 10d. Clinical research / validation
- The measurement features need a validation study against clinical reference
  standards (monofilament, tuning-fork/quantitative sensory testing, clinician
  exams). Design the app to double as the research instrument: e-consent, cohort
  flags, exportable de-identified datasets, IRB-ready audit trail.
- Published validation (post-filing!) is the moat marketing and payers both need.

### 10e. Caregiver / family
- Optional trusted-person view: med adherence, fall alerts, foot-check completion.
  Consent-gated, revocable, audit-logged. Big differentiator for the 70+ segment.

---

## 11. Agile operating model

- **Dual-track:** a discovery track (interviews with patients + podiatrists/
  neurologists, prototype tests) feeding a delivery track on 2-week sprints.
- **Personas** fall straight out of the lenses above: the 62-y/o diabetic patient,
  the 45-y/o CIPN survivor, the podiatrist, the caregiver.
- **Phasing proposal:**
  - **Phase 0 (now):** ADRs for the load-bearing decisions (platform, regulatory
    posture, business model, data model), clickable prototype, patent counsel
    engaged, provisional(s) drafted.
  - **Phase 1 — MVP (wellness tier):** symptom/flare logging + body map, medication
    & titration tracking, foot-check photo log, insights v1 (trends), education,
    visit-prep export. iOS first if the platform ADR lands that way.
  - **Phase 2 — measurement (research mode):** balance/sway test, vibration
    perception test with device calibration, gait metrics ingestion; IRB'd
    validation study.
  - **Phase 3 — clinician & revenue:** clinician review portal, RTM workflow,
    Android parity, caregiver view.
- **Definition of Done includes:** accessibility check, privacy/PHI check, audit-log
  coverage, ADR updated if a decision changed. Backlog in GitHub Issues/Projects on
  this repo.

## 12. DevOps operating model

- **Repo shape:** this monorepo — `apps/` (mobile), `backend/`, `infra/`, `docs/`.
- **CI/CD:** GitHub Actions from the first line of code — lint, tests, dependency and
  license scanning (enforces hard rule §4 via SBOM + license checker), secret
  scanning, SAST. Branch protection on `main`; PRs are the only path in (already a
  hard rule).
- **Mobile delivery:** Fastlane → TestFlight / Play internal track; staged rollouts.
  ⚠️ Any *public* TestFlight/beta counts as disclosure risk — keep betas invite-only
  until filing (Legal lens).
- **Backend/infra:** HIPAA-eligible cloud services under a BAA, IaC (Terraform),
  dev/staging/prod separation, encrypted-at-rest managed Postgres, centralized
  structured logs feeding the audit trail, error tracking only via BAA-capable
  vendors, automated backups with restore drills.
- **Observability doubles as compliance evidence** (SOC 2 lens): build it once.

---

## 13. The three decisions that gate everything else

1. **Platform strategy** — iOS-native-first (measurement fidelity) vs. cross-platform
   day one (reach). Gates hiring, timeline, and Phase 2 feasibility.
2. **Regulatory posture** — commit to wellness-tier launch + research-mode
   measurements, or aim straight at a cleared-device strategy. Gates claims,
   marketing, and study design.
3. **Business model center of gravity** — B2C subscription vs. clinic-led B2B2C with
   RTM billing. Gates the clinician portal's place in the roadmap.

Each of these becomes an ADR in `docs/decisions/` once the owner decides.
