# BioMech × us — the data streams we can actually use

**Date:** 2026-07-16 · **Status:** strategy + integration review, grounded in real BioMech
materials received from the owner (company deck + live Balance/Gait test reports).
**Companions:** [`../requirements/biomech-health/2026-07-11-biomech-lab-report-format.md`](../requirements/biomech-health/2026-07-11-biomech-lab-report-format.md)
(report structure), [`../requirements/biomech-health/2026-07-11-biomech-lab-portal-review.md`](../requirements/biomech-health/2026-07-11-biomech-lab-portal-review.md)
(portal/orders), [`ai-augmented-protocol-feasibility.md`](ai-augmented-protocol-feasibility.md) (the moat).

> **Source & IP note (CLAUDE.md §3, §5).** Based on BioMech's confidential 2026 company
> deck and three live test reports (synthetic "Test Test" patient). Their product,
> scoring formulas, sensor design, and branding are **their IP** — we transcribe
> *structure, metrics, and data hand-offs* only, design our own surfaces clean-room, and
> commit **no** report images or PHI. Example numbers are format illustration, detached
> from any real patient. Not investment, clinical, or regulatory advice.

## TL;DR

- **"BioMech is a daily activity" = the RKM at-home product.** RKM = **Remote Kinematic
  Measurement**. At home ($180/patient/month), the **patient self-administers** short
  tests that **auto-upload to the referring clinician** — a *standardized daily
  assessment*, producing the same rich metric set as the in-clinic reports. Cadence is
  **once daily: one gait test + one balance test.** This is the high-value case: a genuine
  **daily functional measurement stream**, not a gamified engagement score.
- **Two tiers, and both matter (owner's framing).** BioMech is the **clinical tier**
  (structured, device-grade gait/balance). Our **ADLs are the real-world tier**, sourced
  from a **wearable (watch)** — passive, continuous, ecological function. The product's
  outcome story for the **aging population** is proving a patient improves in **both**:
  clinical scores (BioMech) *and* real-world ADL scores (watch). Clinical gain that shows
  up in daily living is the payer/value-based-care argument (falls avoided, aging in
  place).
- **The sensor is the moat feedstock.** BioMech's proprietary sensor captures **12 vectors
  at 100 Hz**. If we can reach that (API/SDK — owner says *"we can probably have API
  access"*), a **daily, device-grade, multimodal** stream is exactly the proprietary
  longitudinal dataset the feasibility doc identified as the durable moat.
- **⚠️ Engineering finding: our PDF parser does not match the real reports.** The real
  reports are **space-tabular, not colon-delimited**, and their metric set
  (Average Speed, Average Movement, Average Position, Impact Symmetry, Support Ratio,
  Pelvic Tilt…) **does not overlap** with the codes our parser hard-codes
  (sway_velocity, sway_area, gait_speed, step_time_symmetry). As written, `parser.py`
  would extract **almost nothing** from a real BioMech report. This needs correcting —
  and given probable API access, the right fix is to **pivot to the API/SDK path**
  (`device_measured`) rather than harden PDF scraping.
- **Adherence vs. measurement is now resolved.** RKM yields a real daily *performance*
  measurement → it can feed the NSI **Function** domain at high frequency. Completion /
  transmission-day counts stay **adherence** → Confidence + RTM/RPM billing, out of the
  score. Two different signals from one activity; keep them separate (the current design's
  instinct was right).

## 1. What BioMech is (from the 2026 deck)

- **Company:** BioMech Health (Richmond, VA). "AI-driven motion analytics platform —
  motion as a clinical biomarker." Clinically validated, **15 U.S. patents**, ~$30M
  invested, $119.8M pre-money (raising Series C). Leadership ex-Dominion Diagnostics.
- **Sensor / signal:** proprietary wearable IMU — **"12 vectors of data, 100 times per
  second."** Balance test sensor at **Head–Front**; gait at **Lower Back**.
- **Three product/revenue lines:**
  1. **BioMech Lab In-Clinic** — clinician runs tests in office. ~$9/test (→$12 in 5/26),
     ~2 tests/visit. **Episodic.**
  2. **BioMech Lab at Home (RKM — Remote Kinematic Measurement)** — kit shipped on a
     clinician **order**; **patient selects a test, runs it, results auto-upload** to the
     clinician; orders expire and are returned/renewed (30-day cycles). **$180/patient/
     month. This is the daily stream.**
  3. **Remote Assist** — real-time biofeedback/therapy (the largest projected revenue
     line by 2028).
- **Workflow spine:** Order # + Client (clinic) + Date of Service + Test ID + Run By —
  the clinical/billing record BioMech Lab is built around (RTM/RPM-shaped, per the portal
  review).

This answers three previously-open owner questions: **RKM = Remote Kinematic Measurement**;
the at-home activity **is** a self-administered daily test; and the sensor is a **12-channel
100 Hz IMU**.

## 2. The real report ground truth (metric catalog)

Transcribed from the three live reports (DIA-C83706/07/09, synthetic patient). This is what
a "BioMech recording" actually contains — and what our ingestion must target.

**Balance Individual Test Report** — one report per *test condition*. Columns:
Units | Result | Reportable Range | Normal Value.

| Metric | Unit | Example | Notes |
|---|---|---|---|
| **Balance Score** (composite) | % 0–100 | 93 | ↑ = lower fall risk; factors Speed+Movement+Position |
| Average Speed | deg/s | 1.9 | ideal 0 |
| Average Speed % Normal | % 0–100 | 97 | population-referenced |
| Average Movement | deg | 1.4 | ideal 0 |
| Average Movement % Normal | % 0–100 | 97 | |
| Average Position (3D) | deg | 4.1 (RF) | dominant-direction tag |
| Average Tilt (+ L/R, F/B) | deg | 3.6 | |
| Average Rotation L/R (+ Range) | deg | 1.9 (R) | |
| Average Position % Normal | % 0–100 | 80 | |

**Test conditions are a first-class axis.** The two balance reports differ only by protocol:
*"Parallel Apart, Eyes Open, 30s"* (score 93) vs *"Parallel Together, Eyes Closed, 30s"*
(score 92). This is an **mCTSIB-style battery** (stance × vision × surface). **Eyes-closed
stance is directly neuropathy-relevant** — it removes vision so balance depends on
proprioception + vestibular; DPN degrades proprioception, so the *eyes-open − eyes-closed*
gap (a Romberg-type ratio) is a candidate neuropathy-specific signal. We must capture the
**condition**, not collapse conditions into one "balance score."

**Gait Individual Test Report:**

| Metric | Unit | Example | Notes |
|---|---|---|---|
| **Gait Score** (composite) | % 0–100 | 85 | ↑ = more normal gait; factors Pelvic Tilt + Impact/Support symmetry |
| Total Steps | count | 70 | |
| Average Step Length | **feet** | 2.1–2.5 ref | note: feet, not cm |
| Cadence | steps/min | 97 (norm 100) | |
| Impact L/R + Impact Symmetry % Normal | % | 47/53 → 96 | |
| Single/Double Support + Support Ratio % Normal | % | 70/30 → 100 | norm ~4:1 |
| Single Support L/R + Symmetry % Normal | % | 49/51 → 96 | |
| Pelvic Tilt (dir, L/R, F/B) + Pelvic Tilt % Neutral | deg / % | 7.0 (RB) → 62 | |

**Two gifts in this format:** (a) BioMech already provides **"% Normal" population-referenced
0–100 values** for most metrics — that is the normalization our NSI hand-rolls in
`composite.py`'s reference bands; we could consume theirs directly. (b) The metrics are
**richer and more neuropathy-informative** than a single score (gait symmetry, support
timing, eyes-closed sway) — good raw material for a neuropathy-specific composite.

## 3. ⚠️ Engineering finding — the parser must change

`backend/app/biomech/parser.py` was built against an assumed format that the real reports
contradict:

| Assumption in `parser.py` | Reality in the reports |
|---|---|
| Lines are `label: value unit` (colon-delimited) | **Space-tabular:** `Balance Score  Percent  93  0 - 100` — the only colons are in `Patient:`, `Test ID:` headers |
| Metrics: `sway_velocity`, `sway_area`, `gait_speed`, `step_time_symmetry` | **None of these exist.** Real: Average Speed, Average Movement, Average Position, Impact Symmetry, Support Ratio, Single-Support Symmetry, Pelvic Tilt % Neutral |
| `step_length` in **cm**; `gait_speed` in **m/s** | Step Length in **feet**; **no gait-speed metric at all** |
| One balance score per report | One report **per test condition** (eyes open/closed, stance) |

**Consequence:** run against a real report, the current parser matches `Balance Score` and
`Cadence` at best (and only if the colon-split were fixed) and drops the entire rich set.
It is not production-usable for real BioMech data.

**Recommendation:** since API access is probably available, **pivot to the API/SDK path**
(`origin=device_measured`, already reserved in ADR-0014) and treat structured ingestion as
the primary route. Keep a PDF fallback only if needed, and if so **rebuild the parser
against the real tabular format + real metric catalog above**. This is an ADR-level decision
(supersedes the parser's format assumptions) and a follow-up code task — flagged here, not
bundled into this review.

## 4. The data-stream inventory (enriched with ground truth)

| # | Stream | Frequency | Fidelity | Status today | Feeds | Unlock |
|---|--------|-----------|----------|--------------|-------|--------|
| 1 | **In-Clinic test reports** (balance/gait) | Episodic (per visit) | Device-grade | ⚠️ parser mismatch (see §3) | NSI Function (clinical) | Fix parser **or** API |
| 2 | **RKM at-home daily self-tests** (1 gait + 1 balance/day) | **Daily** | Device-grade | ❌ not ingested | NSI Function (clinical, high-freq) | API/SDK + order feed |
| 3 | **Raw sensor** (12 vectors @ 100 Hz) | Continuous | Highest | ❌ not accessed | **Moat / ML feedstock** | SDK/raw access |
| 4 | **Per-metric "% Normal"** (population-referenced) | With each test | Derived | ❌ (we hand-roll our own) | NSI normalization | Same feed |
| 5 | **Test conditions** (eyes open/closed, stance) | With each test | — | ❌ (parser ignores) | Neuropathy-specific signal (Romberg gap) | Capture condition per obs |
| 6 | **RKM order lifecycle** (order/expiry/renewal) | Event | — | ❌ | Capability activation + RTM billing | Portal/order API |
| 7 | **Clinician review / transmission days** | Event/daily | — | ❌ | Adherence → Confidence + RTM billing | Portal API |
| 8 | **Remote Assist** (real-time biofeedback) | Real-time | — | ❌ (their line) | Future therapy loop | Later |
| 9 | **Wearable ADLs (watch)** — real-world function | **Continuous** | Consumer-grade | ⚠️ today self-reported, not sensed | NSI Function (**real-world tier**) | Watch/HealthKit/Health Connect ingest |

Streams 1–8 are **BioMech (clinical tier)**; stream 9 is **ours (real-world tier)** — the
two sources the outcome story pairs. Our research-grade `Observation` model already
accommodates all of this without a schema change: new `code`s per metric,
`origin=device_measured` (BioMech/API) or `device_measured` from the watch, the **test
condition** as a coded qualifier in `code`/`quality`, and BioMech's **% Normal** stored
alongside the raw value. Streams 3 and 5 are the neuropathy-differentiating clinical
signals; stream 9 is what proves the clinical gain reached daily life.

> **Honesty on the watch tier.** Today our "ADLs" are the **self-reported** 0–4 check-in
> items (`adl_walking/stairs/balance_confidence`), not sensor-derived — so stream 9 is a
> **design direction**, not current state. Consumer-watch metrics (steps, real-world gait
> cadence, active minutes, sit-to-stand) are **consumer-grade**, not clinical, and mapping
> them to an "ADL function" score is itself a modeling + validation task. The value is the
> *pairing* (clinical ↑ **and** real-world ↑), not treating watch data as clinical truth.

## 5. What this means for the NSI

- **Split Function into two tiers.** The Function domain should distinguish
  **clinical function** (BioMech gait/balance) from **real-world ADL function** (watch).
  They answer different questions — *can you perform the test* vs *do you actually move
  well in daily life* — and the compelling outcome for the aging population is when **both
  rise together**. Options: surface them as two sub-scores under Function, or as parallel
  tracks on the card (a "clinical" line and a "daily-life" line). This is an ADR-0034
  refinement to design clean-room; do **not** silently average a consumer-grade watch
  signal into a device-grade clinical one without weighting for fidelity.
- **A daily, device-grade Function stream (stream 2)** upgrades the clinical tier from a
  handful of episodic points to a **curve** — which is what actually powers 30-day trend
  detection, responsiveness, and MCID. Frequency helps the science regardless of ML.
- **Neuropathy-specific sub-signals** worth adding to the composite design (clean-room,
  our own weighting): the **eyes-open − eyes-closed balance gap** (proprioceptive proxy),
  **gait symmetry** (impact + single-support), and **cadence/step-length decline**.
- **Consume BioMech's "% Normal"** (stream 4) instead of, or alongside, our illustrative
  reference bands — better-calibrated normalization, still combined by *our* neuropathy
  weighting (we must not copy their composite formula — §6).
- **Adherence stays out of the number.** RKM completion / transmission days (stream 7)
  inform **Confidence** and **RTM/RPM billing**, never the NSI score. Doing the test more
  often isn't better nerve health; the current `composite.py` guard stands.

## 6. Moat & clean-room

- **Moat (ties to the feasibility doc):** a **daily 12-vector-100 Hz multimodal record**
  (symptoms + at-home kinematics + labs), consented and longitudinal, is precisely the
  proprietary dataset no competitor can copy. Honesty carries over: the *ML-fusion
  accuracy gains* remain **unverified** (feasibility doc Part B2) — this is moat
  *substrate*, and the near-term proven levers are frequency (responsiveness) + IRT/CAT,
  not yet a validated fusion model.
- **Clean-room:** BioMech's Balance/Gait Score **formulas and sensor are their IP.** We
  ingest their *outputs* (metrics, % Normal) under the agreement and build our **own
  neuropathy-weighted composite** on top — general-balance/gait scoring is theirs; a
  DPN-specific index is ours. No report layouts, scoring code, or branding copied.

## 7. Recommended path & open decisions

**Recommended integration path: API-first.**
1. **Confirm the API/SDK** with BioMech — endpoints/schema for (a) per-test metrics +
   % Normal + condition, (b) order lifecycle, (c) transmission/review events, and ideally
   (d) raw 12-vector access. (Owner: "probably" available — pin it down.)
2. **ADR: pivot BioMech ingestion to `device_measured` (API)**, superseding the PDF
   parser's format assumptions; keep PDF only as a fallback and, if kept, rebuild it to
   the real tabular catalog (§2–§3).
3. **Model the RKM order** as the clinical activation (per portal review) — order →
   capability → expiry/renewal.
4. **Design the neuropathy composite v2** to use the richer metrics + condition gap,
   clean-room (§6), feeding the NSI Function domain daily.

**Sensor posture — the owner's framing largely resolves it into a division of labor:**
**BioMech's kit/sensor does the clinical tier** (structured daily gait + balance), and
**our watch/phone does the real-world tier** (passive ADL monitoring). That is
**complementary, not competing** — good for the license relationship — and it means we
**ingest** BioMech's clinical feed (API) rather than rebuild clinical tests on the phone.
The narrower open question for the ADR: which **watch metrics** define our ADL score
(steps, real-world cadence, active minutes, sit-to-stand, gait variability), on which
platform (Apple HealthKit / Android Health Connect), and how they map to a validated
real-world-function measure.

## 8. Owner questions — status

- ✅ **RKM meaning** — Remote Kinematic Measurement (at-home self-test product).
- ✅ **Is the daily activity a measurement or a game?** — a standardized daily self-test
  (real measurement).
- ✅ **Sensor** — proprietary IMU, 12 vectors @ 100 Hz.
- ✅ **All data / codes** — confirmed in the reports (metric catalog, §2).
- ✅ **Daily cadence** — once daily: **1 gait + 1 balance** test.
- ✅ **Sensor posture (division of labor)** — BioMech kit = clinical tier; **our watch =
  real-world ADL tier** (complementary). Narrower ADR remains on *which* watch metrics
  define the ADL score (§7).
- 🟡 **API/SDK access** — "probably"; confirm endpoints/schema + whether raw 12-vector is
  exposed.
- 🟡 **Watch ADL modeling** — which metrics + platform (HealthKit / Health Connect), and
  validation of watch-derived real-world function (today ADLs are self-reported, §4).
- 🟡 **RTM/RPM codes + transmission-day counting** — confirm for billing (streams 6–7).
