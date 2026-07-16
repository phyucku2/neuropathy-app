# ADR-0035 — Phone-base ADLs + the Apple Health / Android Health Connect bridge

- **Status:** Proposed (owner-directed; native scope decisions pending — see §Open)
- **Date:** 2026-07-16
- **Builds on:** ADR-0023 (Capacitor, Android-first), ADR-0024 (platform seams, Cap-6
  plugin pinning), ADR-0025 (native shell init), ADR-0013 (enforced feature toggles),
  ADR-0006 (Observation model + ADL check-in), ADR-0034 (Neuropathy Status Index)
- **Companion:** [`../product/biomech-data-streams.md`](../product/biomech-data-streams.md)
  (the two-tier model: BioMech clinical tier + wearable/phone real-world ADL tier)

## Context

The data-streams review established two tiers of Function signal: **BioMech = clinical**
(structured daily gait + balance, device-grade) and **ADLs = real-world** (how the patient
actually moves in daily life). The owner's direction sharpens the real-world tier:

> **The phone is the base; the watch is a good-to-have option.** And we need to bridge to
> both **Apple Health** and **Android Health**.

Today our "ADLs" are the **self-reported** 0–4 check-in items (`adl_walking/stairs/
balance_confidence`, ADR-0006). This ADR moves the ADL tier toward **sensor-derived
real-world function** imported from the platform health stores, with self-report as the
fallback where sensing isn't available.

## What a phone can track vs. a watch (the base decision)

The key finding — and an **honest platform asymmetry** that shapes "phone as base":

### iOS — iPhone alone is rich (HealthKit + CoreMotion)

The iPhone (iPhone 8+, iOS 14/15, carried body-coupled in a pocket/belt with height
entered; computed only on flat overground walking bouts, not all-day) computes **Mobility
metrics** without a watch. **Verified (deep-research pass, 2026-07-16) — and validity is
uneven, which changes how we use them:**

| Metric | Source | Phone-alone validity (verified) | BioMech gait parallel |
|---|---|---|---|
| Walking **Speed** | iPhone | **Strong** — ICC ~0.85–0.93 vs pressure-mat/IMU | gait pace |
| Walking **Step Length** | iPhone | **Good** (adults/seniors) — ICC ~0.76–0.85 | Average Step Length |
| Steps, Distance, Flights, Stair speed | iPhone | Quantity (well-established) | Cadence / Total Steps |
| Walking **Asymmetry** % | iPhone | **Weak** — significantly under-reported phone-alone | Impact / Single-Support Symmetry |
| **Double Support Time** % | iPhone | **Weak** — ICC ~0.42–0.58, up to ~32% error in seniors | Support Ratio (single:double) |
| Walking **Steadiness** | iPhone | Fall-risk classifier; validated on Apple Heart & Movement Study (vendor) | balance/fall-risk |
| Six-Minute Walk (estimated) | iPhone | endurance (context-limited) | — |

**Corrected standout (this supersedes the earlier "mirrors BioMech" framing):** the iPhone
measures the *same gait constructs* a wearable IMU does, but **only speed and step-length
are reliable phone-alone.** The **gait-quality** metrics (asymmetry, double-support) are
**poor-to-moderate and biased phone-alone** — so a phone-first design must **lean on
speed + step-length** and treat asymmetry/double-support/steadiness as **advisory or
watch-augmented**, never as device-grade truth.

> **Biggest external-validity caveat (verified):** every phone-gait accuracy figure above
> comes from **healthy / general-population adults, not a DPN or impaired-gait cohort** —
> and Apple's own figures are first-party (an upper bound). Accuracy in our actual target
> population (abnormal, slow, unsteady gait) is **unverified** and could be worse. This is
> a validation task before any clinical weight is placed on phone-derived gait, and it
> reinforces the fidelity-weighting rule below.

**Watch (Apple Watch) adds — the "good-to-have":** continuous heart rate + HRV, cardio
fitness (VO₂max), workouts, fall detection, and more continuous/accurate sampling. It
*enhances* the mobility picture but is **not required** for the core gait metrics.

### Android — the phone (via Health Connect) is thinner on gait quality

Android **Health Connect** aggregates **Steps, Distance, Speed, Active/Total Calories,
Exercise sessions, Floors, Elevation, Heart Rate (from a wearable), Sleep**. It does
**not** define standard *gait-quality* types — **no walking asymmetry, double-support, or
steadiness**. So an Android phone via Health Connect gives **ADL volume + pace** (steps,
distance, speed, active minutes), not the gait-quality set the iPhone provides. Getting
gait quality on Android would require processing **raw accelerometer/gyro** ourselves (a
substantial, separately-validated undertaking) — out of scope for v1.

> **Consequence for "phone as base":** the base is **real but uneven** — strong,
> BioMech-parallel on iOS; volume/pace-only on Android v1. We should design the ADL score
> to degrade gracefully: use the richest metrics a platform offers, and never claim
> gait-quality on Android that the platform can't produce.

## Decision

1. **The real-world ADL tier is phone-base**, sourced from **Apple HealthKit (iOS)** and
   **Android Health Connect**, with the **watch as an optional enhancement** (continuous
   HR/HRV, cardio fitness, higher-frequency sampling) — never a requirement.
2. **Bridge via a platform seam**, following the ADR-0024 pattern: a pure-logic,
   injectable `health` accessor (`src/native/health.ts`) with a **web mock** + **native**
   implementations, so every mapping/consent decision is unit-testable off-device and the
   web/E2E paths never touch a native plugin.
3. **Gated by an enforced capability** (`health_ingest`, ADR-0013), **default off**,
   **consent-gated** — health import is opt-in and server-enforced, like `ingest_symptoms`.
4. **Imported samples become research-grade Observations** (ADR-0006): `origin=
   device_measured`, a distinct `SourceType` (`wearable`) so phone/watch data pools
   separately from BioMech (`biomech`) and self-report (`adl`); per-metric codes;
   provenance in `quality` (platform, source device, whether phone- or watch-derived);
   idempotency by sample identity + time. The self-reported 0–4 items remain as the
   fallback where sensing is unavailable.
5. **These feed the NSI Function domain's real-world sub-tier** (ADR-0034 refinement),
   **weighted for fidelity** — a consumer-grade watch/phone signal is never silently
   averaged into a device-grade clinical one.

### PHI & privacy posture (non-negotiable)

Health-store data is **PHI**. Least-privilege scopes (request only the metrics we map),
explicit consent, **no health values in logs/metrics/audit** (counts + references only,
per data-standards), and on iOS respect that HealthKit read access is not introspectable
(the app must handle "granted but empty"). Revoking the capability stops import; existing
Observations follow the normal lifecycle.

### Plugin selection (Cap-6, permissive licenses — ADR-0024)

There is **no official Capacitor health plugin**. We will pin **vetted community plugins**
(permissive SPDX on the allowlist, Capacitor-6 peer range, `cap sync` warning-free): a
**Health Connect** plugin for Android and a **HealthKit** plugin for iOS (or a unified
`capacitor-health` if it satisfies both cleanly). Exact packages pinned at build time in
the phase that adds them, not before.

## Phased plan

- **Phase 1 — seam + contract (buildable now, web-first, no native deps).** `health.ts`
  seam, the `health_ingest` capability, the `wearable` SourceType + code catalog + the
  Observation mapping, a web mock, and full unit tests. Ships through CI with **no native
  dependency** — mirrors how EMR-connect/reminders were built seam-first, native deferred.
- **Phase 2 — Android Health Connect (native).** We are Android-first (ADR-0023): wire the
  Health Connect plugin, permissions/consent UI, import steps/distance/speed/active-minutes
  → ADL **volume** signals.
- **Phase 3 — add iOS + HealthKit.** Add the Capacitor **iOS platform** (not present today)
  and the HealthKit plugin to unlock the **gait-quality mobility metrics** (the
  BioMech-parallel set) — the strongest form of "phone as base."
- **Phase 4 — watch-optional enhancements.** HR/HRV, cardio fitness, continuous sampling
  where a paired watch is present.

## Honesty invariants

- **Consumer-grade, not clinical.** Watch/phone-derived ADL is a real-world *function
  proxy*; validating it as a measure (and mapping raw metrics to an ADL score) is its own
  task. Non-diagnostic; the NSI stays a v1 index pending validation (ADR-0034).
- **No platform overclaiming.** Android v1 reports volume/pace, not gait quality.
- **Complementary to BioMech, not competing.** BioMech's kit does the clinical tier; our
  phone/watch does the real-world tier — good for the license relationship.

## Open (owner/decisions pending)

1. **iOS timing.** The richest phone-base metrics are iOS-only, but we are Android-first
   and have **no iOS platform yet**. Add iOS in Phase 3 as planned, or accelerate it given
   the metric upside? (Recommendation: seam (P1) → Android (P2) → iOS (P3), but don't let
   iOS lag long — the "phone as base" story is strongest there.)
2. **v1 metric set** — confirm the phone-derivable set above as v1 (steps/speed/step-length
   + iOS asymmetry/double-support/steadiness; Android volume/pace).
3. **Health-store catalog verification** — ✅ done (deep-research pass, 2026-07-16):
   iPhone-alone metric set + validity confirmed; Health Connect gait-quality gap confirmed.
   **Remaining, and now the priority open question:** accuracy of iPhone gait metrics in a
   **DPN / impaired-gait population** (all published figures are healthy adults) — a
   validation task before clinical weight is placed on phone-derived gait.
