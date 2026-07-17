# Buildable roadmap — one-PR-sized implementation specs

> **AI-drafted specs, to be reviewed before implementation.** Each is scoped to roughly one
> PR to match the repo's small-PR / merge-between discipline. File paths, ADR references, and
> test lists are carried verbatim from the drafting pass; treat the **open decisions** as
> gates that need a human (owner / clinical / regulatory) before that work ships.

These five items build directly on what already exists (ADR-0034 NSI, ADR-0035 wearable
ingestion + health seam, ADR-0036 BioMech real format). They are ordered roughly by
independence, not priority.

---

## Spec 1 — Android Health Connect connector (ADR-0035 Phase 2, PR-A)

**Rationale.** The health seam (`health.ts`), the `HealthPlugin` interface, `syncHealth()`, the
`/wearable` contract, and the enforced `ingest_wearable` toggle already exist and are unit-tested
off-device. The missing piece to make Android mobility flow is a concrete Health Connect adapter
+ its pure record→sample mapper + Android-only bootstrap registration — mirroring how
reminders/EMR were built native-after-seam.

**Approach (scoped small).** Pin a vetted Cap-6-compatible, permissively-licensed Health Connect
plugin; add `frontend/src/native/healthConnect.ts` satisfying `HealthPlugin`
(`isAvailable`/`requestPermissions`/`queryMobility`) with least-privilege scopes (steps /
distance / speed only); a **pure** `healthConnectRecordToSample()` mapping StepsRecord→
`wearable_steps`, DistanceRecord→`wearable_walking_distance`, SpeedRecord→`wearable_walking_speed`,
carrying `metadata.id`→externalId for idempotency; register Android-only in `nativeShell.ts`. Emit
**nothing** for gait-quality metrics — Health Connect has no asymmetry/double-support/steadiness
types (the documented platform gap, asserted in tests). Add manifest permissions + rationale
intent; bump `minSdk` to the plugin floor.

**PR size:** medium. **Depends on:** a follow-up small PR-B (Settings Health card that calls
`syncHealth()` — no non-test caller exists today), a public privacy-policy URL, and Google Play
Health Connect declaration (release gate, not merge gate).

**Files:** `healthConnect.ts` (+ test), `nativeShell.ts`, `package.json`/lockfile,
`AndroidManifest.xml`, `variables.gradle`, `capacitor.config.ts`.

**Open decisions:** exact plugin to pin (eng + license review); confirm Android v1 = volume/pace
only (product/clinical); how to source walking speed (generic SpeedRecord vs distance/time);
acceptable `minSdk` floor; whether PR-B ships in the same train.

---

## Spec 2 — iOS platform + HealthKit (ADR-0035 Phase 3; LARGE → 4 PRs; this details PR-1)

**Rationale.** "Add iOS + HealthKit" bundles four independently-risky things — a new native
platform, a plugin pin, Apple entitlement work, and a macOS CI runner — so it must be split. The
safe first PR mirrors ADR-0023's Android-scaffolding-only pattern: add the platform, change no
behavior, unblock the rest.

**The split.** PR-1 = add the Capacitor iOS platform, scaffolding only (this spec). PR-2 =
select + pin a HealthKit plugin (or write a thin first-party Swift plugin). PR-3 = the HealthKit
connector (map HK samples → `WearableMetric`, Info.plist usage strings, entitlement,
`setHealthPlugin()` wiring). PR-4 = the Settings health-sync card + trigger (currently **missing
even for Android** — Phase 2 never wired it).

**PR-1 approach.** Add `@capacitor/ios` pinned to the core version; `npx cap add ios` (Mac only);
an `ios` block in `capacitor.config.ts`; commit the `frontend/ios/` skeleton with a strict
`.gitignore` (no Pods/build/signing material); exclude `ios/` from prettier/eslint; add a
`cap:open:ios` script; add a **separate `mobile-ios` CI job on `macos-14`** doing an unsigned
`iphonesimulator` `xcodebuild` (the honest analog of Android's debug-assemble); update ADR-0023 /
ADR-0035 status.

**Key later constraint (design PR-1 with it in mind).** HealthKit **read** authorization is not
introspectable — `authorizationStatus(for:)` reports write only. So `requestPermissions()` cannot
truthfully return `granted=false` on denial; denial masquerades as `no-data`. The seam's
`permission-denied` branch is effectively unreachable on iOS — the UX copy must own that ambiguity.

**PR size:** large (this PR-1: small-to-medium). **Depends on:** a Mac with Xcode/CocoaPods; an
Apple Developer account under the AHWG publisher (ADR-0023 deferred iOS pending the DUNS/Apple-ID
switch); macOS CI budget.

**Open decisions:** confirm iOS is unblocked now (owner/business); permanent iOS bundle id;
macOS CI cost policy (every push vs path-filtered); v1 HealthKit metric set; granted-but-empty UX
copy; regulatory sign-off for reading fall-risk-adjacent signals into a non-diagnostic app;
plugin vs first-party Swift.

---

## Spec 3 — NSI Function two-tier: fold fidelity-weighted wearable data into the composite (ADR-0034 refinement)

**Rationale.** The Function domain currently flat-averages device-grade BioMech scores with
self-reported ADLs and ignores wearable data. Splitting Function into a **clinical** sub-tier and
a **fidelity-weighted real-world** sub-tier (per ADR-0035 §Decision.5) lets us fold in wearable
ADLs **without ever averaging a consumer-grade signal as device-grade.** Fidelity is deterministic
per code via the wearable catalog, so the change lives in the composite layer + one ADR — no
contract/DB changes.

**Approach.** New ADR-0037 (Proposed) documenting that the headline score *structure* changes
(Function stops being a flat mean). Add a pure `fidelity_for_code()` helper sourced from
`WEARABLE_METRICS`; add a `SubTier` enum; combine each present sub-tier's intra-weighted mean with
`_SUBTIER_WEIGHTS={clinical:1.0, real_world:<discount>}` **renormalized over present sub-tiers**
(absent sub-tier dropped, never imputed 0). Reliable metrics (`wearable_walking_speed`,
`wearable_step_length`) enter the score; the three advisory metrics
(`asymmetry`/`double_support`/`steadiness`) stay **trend-only, excluded from the score.**

**PR size:** medium. **Files:** `composite.py`, `ingestion/wearable.py`, ADR-0037,
`test_trajectory_composite.py` (expected ints shift, e.g. full-three-domain 72 → ~71).

**Open decisions:** the cross-tier discount value (biostat sign-off); intra-tier fidelity weights
and whether volume metrics enter the v1 score at all; wearable normalization bands (DPN-aware,
physician-signed); regulatory posture of consumer-grade input to a non-diagnostic index.

---

## Spec 4 — Symptom item-bank + administration seam (IRT/CAT groundwork; deterministic stub)

**Rationale.** Real IRT/CAT needs a calibrated item bank from longitudinal data we don't have,
and a 2-item symptom set **cannot be adaptive at all.** The honest smallest step is a versioned
`ItemBank` abstraction with empty calibration slots + item-selection/scoring Protocols whose only
implementations are deterministic and non-adaptive — refactoring today's scattered symptom
constants onto that seam with **zero behavior change.**

**Approach.** New `backend/app/psychometrics/` package: `item_bank.py` (frozen `ItemCalibration`
with all fields defaulting `None`, `SymptomItem`, `ItemBank.is_calibrated` → False today);
`administration.py` (`FixedOrderSelector`, `SumScoreEstimator` — `is_irt=False`, guarded so a
future half-wired calibration cannot silently claim IRT). Refactor `ingestion/adl.py` so the
symptom codes/alignment/displays **derive from** the bank (single source of truth) with no change
to emitted Observations. Honesty guards in tests: nothing `validated_instrument=True`, no estimate
claims IRT while the bank is uncalibrated; a parity test vs `directionality.py`.

**PR size:** small (genuinely additive backend scaffolding + one safe refactor). **Files:**
`psychometrics/*`, `ingestion/adl.py`, tests, ADR-0037, `roadmap-status.md`.

**Open decisions (all non-code):** item-bank *expansion* is the real CAT prerequisite (owner +
neurology PI + psychometrician); IRT model choice; who collects the real calibration data;
NTSS-6 licensing beyond "aligned" wording; FDA posture of an adaptive/IRT-scored measure; whether
adaptive administration is even desirable for a ~2-item daily check-in.

---

## Spec 5 — BioMech eyes-open − eyes-closed balance gap as a derived Observation (ADR-0036 follow-up)

**Rationale.** The eyes-open/closed condition is already captured on `biomech_balance_score`
observations (ADR-0036). The smallest honest way to expose the proprioceptive proxy is a
**deterministic derived Observation** (`biomech_balance_eyes_gap`, `origin=derived`) computed from
the same-day condition-tagged pair — mirroring the `adl_daily_score` derived-composite precedent
so it graphs, trends, and carries research-grade provenance for free.

**Approach.** Pure helpers in `biomech/ingest.py`: `classify_balance_condition()` (returns `None`
on both/neither token — never guess), a content-identity import key, and a
`balance_eyes_gap_observation()` with `value = open − closed` (larger positive = more balance lost
without vision = worse). Trigger after the per-metric ingest loop, inside the existing
`ingest_biomech` gate, firing on whichever upload completes the same-day pair (both orders work);
idempotent via the import key; **skip-with-warning** on same-day ambiguity. Register polarity
`lower_is_better`; assert it is **excluded from the NSI** (`_MEASURES`) so it never double-counts
its own source scores.

**PR size:** medium. **Files:** `biomech/ingest.py`, `routes/biomech.py`, `directionality.py`,
`composite.py`, `schemas/biomech.py`, tests, ADR-0037.

**Open decisions:** clinical sign-off on gap polarity + patient-facing label and the meaning of a
negative gap; whether one balance report is always exactly one eyes-state; same-day duplicate
rule (skip vs use-latest); derived-Observation vs virtual signal; whether the gap increments
`imported` or gets its own `derived` count; toggle scope (reuse `ingest_biomech`).

---

*These specs came from an AI orchestration pass and are starting points, not approved work.
Each open decision above is a real gate — several need clinical, regulatory, or business sign-off
before the corresponding PR should merge.*
