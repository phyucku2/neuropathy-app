# BioMech Lab — Test Report Format (transcribed, de-identified)

**Received:** 2026-07-11 (screenshots of live reports, provided by owner)
**Source:** BioMech Lab clinician portal (biomechhealth.com), "Balance Individual
Test Report" and "Gait Individual Test Report" PDFs.

> **PHI HANDLING (CLAUDE.md §5).** The source report images contain patient
> identifiers (name, DOB, patient ID). Per our hard rules, the report images are
> **NOT committed** to the repo. Only the *structure and metric definitions* are
> transcribed below, with all patient identifiers removed. Any example numbers are
> retained only as format illustration, detached from the patient. If we ever need a
> sample report in-repo, it must use fully synthetic data.

This document is the single most important input we've received: it defines what a
**"BioMech data recording"** actually is, and therefore what our **V1 PDF** must
produce and our **V2 API/SDK** must serialize.

---

## Big picture: what BioMech Lab actually is

BioMech Lab is a **wearable-IMU-based movement assessment system** with a clinician
web portal. Clinicians (or staff) run short, protocol-defined balance and gait tests
using a body-worn sensor; the system computes composite scores and detailed
kinematics and renders standardized PDF reports tied to an **Order #** and a
**Client** (clinic).

- **Sensor:** a single wearable inertial sensor. Balance tests place it at
  **Head – Front**; gait tests place it at **Lower Back**. (Position is a recorded
  parameter.)
- **Tests are parameterized protocols.** From the test list: stance (e.g. "Tandem,
  Right Foot Forward"), vision ("Eyes Open"), surface ("Stable Surface"),
  duration ("10 sec"), sensor position ("Head – Front"). Gait uses duration
  (e.g. "30 sec"), distance, and aid status ("No Aid").
- **Every test has a Test ID** (e.g. `AHWG-C114551`) — client-prefixed, sequential.
- **Reports are per-test** ("Individual Test Report"), 2 pages: page 1 = results +
  charts, page 2 = "About This Test" metric definitions.
- **A composite 0–100 score** headlines each report (Balance Score / Gait Score),
  explicitly framed as objective and (for balance) inversely related to fall risk.

This is exactly the phone-as-instrument layer from our brainstorms — except BioMech
already does it with dedicated hardware and an in-clinic/RKM workflow.

---

## Balance Individual Test Report — structure

**Header:** BioMech Lab brand + address/contact; Patient / DOB / Patient ID / Gender;
Date of Service; Client (clinic); Test ID; Order #.

**Protocol line:** stance + vision + duration + surface (e.g. "Tandem Left, Eyes
Open, 10 sec, Static, Stable Surface"); Sensor Location; Actual Duration; timestamp.

**Metric table** (columns: Units | Result | Reportable Range | Normal Value):
- **Composite:** Balance Score — Percent, range 0–100.
- **Speed:** Average Speed (Deg/sec); Average Speed % Normal (Percent, 0–100).
- **Deviation:** Average Movement (Degrees); Average Movement % Normal (Percent);
  Average Position (3 Dimensions) (Degrees, with a dominant-direction tag e.g. "LF");
  Average Tilt (Degrees) with sub-rows Tilt Left/Right and Tilt Front/Back;
  Average Rotation Left/Right (Degrees); Rotation Range (Degrees); Average Position %
  Normal (Percent).
- **Run By:** operator name.

**Charts:** a **Tilt** scatter (Front/Back × Left/Right, degrees, sway cloud) and a
**Rotation** dial (degrees, 0–180 with L/R and a mean value).

**Page 2 "About This Test":** Balance Score = comprehensive calc where higher % =
lower fall risk, factoring Average Speed, Average Movement, Average Position; plus
plain-language definitions of each metric (zero = ideal for deviation metrics).

## Gait Individual Test Report — structure

**Header:** same layout; Sensor Location: **Lower Back**.

**Protocol line:** Gait Duration; Distance; Aid status.

**Metric table:**
- **Composite:** Gait Score — Percent, 0–100 (higher = more normal gait).
- **Steps:** Total Steps; Average Step Length (Feet; normal ref e.g. 2.1–2.5 ft);
  Cadence (Steps/min; normal ref ~100).
- **Impact:** Impact Left/Right (Percent split); Impact Symmetry % Normal.
- **Support Time:** Single/Double Support (Percent split); Support Ratio % Normal
  (normal ref ~4:1); Single Support Left/Right; Single Support Symmetry % Normal.
- **Pelvic Deviation:** Average Pelvic Tilt (Degrees + direction); Pelvic Tilt
  Left/Right; Pelvic Tilt Front/Back; Pelvic Tilt % Neutral.
- **Run By:** operator.

**Chart:** **Pelvic Tilt** scatter (Front/Back × Left/Right sway cloud).

**Page 2:** Gait Score = composite of Pelvic Tilt, Impact Symmetry, Support Symmetry,
Support (Single/Double); plus metric definitions.

---

## Implications — this reshapes our V1 substantially

### 1. Our "BioMech data recording" is a peer of these reports
The V1 PDF we produce should be **structurally compatible** with BioMech Lab's report
language (composite 0–100 score, protocol line, metric table with Result / Reportable
Range / Normal, sway charts, a definitions page) so clinicians reading both don't
context-switch. Our recording is designed independently, but it must *interoperate*
conceptually. This is a strong argument for the structured **session object**
(Brainstorm #2): score + protocol + metrics + normative ranges + chart series.

### 2. Sensor question is now central (needs owner answer)
BioMech uses a **worn IMU at specific body locations** (head, lower back). Our app has
**phone/watch IMUs**. Three possible V1 postures:
- **(A) Phone-as-sensor:** replicate balance/gait protocols using the phone's IMU
  (phone held to chest/head or in a pocket at the low back). Cheapest, no hardware,
  but different sensor placement → **our normative ranges/scores must be our own**,
  not BioMech's (their 0–100 is calibrated to their device/position). New validation
  needed. Highest invention value.
- **(B) Ingest BioMech sensor data:** our app pairs with / imports from BioMech's
  existing sensor and we render/track it. Fastest clinical fit, least novel, and
  depends entirely on their API/SDK (which is the V2 thing).
- **(C) Both:** phone-native for B2C/home; ingest for clinics already on BioMech
  hardware.
> **Owner decision needed — this gates the entire measurement architecture.** It's
> an ADR. My read: **(A) phone-native is where the patentable IP and the B2C story
> live**, with (C) as the clinical bridge. But it hinges on whether BioMech wants us
> to extend their hardware or leapfrog it with the phone.

### 3. Protocol library is now concrete
We can define our balance/gait test protocols using the same parameter axes BioMech
uses (stance, vision, surface, duration, sensor position; gait duration/distance/aid)
— these are clinical-standard (mCTSIB-style balance conditions, standard gait
metrics), i.e. public-domain protocol design, not BioMech IP. Good: our "digital
assessment prescription" capability can offer a recognizable protocol menu.

### 4. Composite-score design is an invention surface (do it independently)
BioMech's Balance/Gait Scores are their formulas. **We must not copy their scoring.**
Designing our **own** neuropathy-weighted composite (e.g. fusing sway + gait
variability + self-reported sensory maps — the Brainstorm #1 fall-risk candidate) is
both required for clean-room and is a prime `> INVENTION CANDIDATE`. Ours should be
neuropathy-specific, where BioMech's appears general-balance/gait.

### 5. Clinical workflow vocabulary confirmed
Order # + Client + Date of Service + Run By + Test ID = the clinical record spine.
Our clinical version's recordings should carry the same identifying spine so they
drop into a clinic's existing chart/billing flow. (Reinforces modeling clinical
activation as an **order**, per the portal review.)

---

## Updated questions for owner / BioMech Health

1. **Sensor posture (the big one):** For our app, do we (A) use the phone as the
   sensor, (B) ingest BioMech's hardware data, or (C) both? Does BioMech *want* a
   phone-native competitor to their sensor, or a companion to it?
2. Is BioMech's sensor a single IMU? Is there an existing pairing API/SDK (this is
   likely the V2 "SDK" they referenced)?
3. Are the Balance Score / Gait Score formulas proprietary to BioMech (assume yes →
   we build our own)?
4. Should our V1 PDF **match their report layout family** for clinician continuity,
   or be visually distinct (our brand)? (Layout can be functionally similar without
   copying their design — confirm intent.)
5. Confirm "RKM" meaning and how a recording attaches to an order in their portal.
