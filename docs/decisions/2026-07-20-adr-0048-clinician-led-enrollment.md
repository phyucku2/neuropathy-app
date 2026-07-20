# ADR-0048 — Clinician-led enrollment & activation ("order → ship → activate → follow-up") (spec)

- **Status:** Proposed (spec — not built). The on-ramp for the "clinician as sales force" model:
  a clinician **orders**, a **package ships**, the patient **activates** from any of several
  touchpoints, and the **office follows up**. Reuses the existing patient↔clinic consent primitive
  (ADR-0005/0012/0020); adds a new-patient front door, an identity match on **name + DOB + Medicare
  number**, and an office activation worklist. **Real Medicare numbers are PHI — this ADR is gated on
  the executed BAA and the HIPAA hardening it triggers.**
- **Date:** 2026-07-20
- **Builds on:** ADR-0005 (`ClinicConnection` pending→active→revoked lifecycle + `Initiator`),
  ADR-0012/0020 (the single `_may_read_patient` consent predicate; non-enumerating invites),
  ADR-0017 (Fernet-encrypted vault + rate limiting), ADR-0047 (caregiver invite-by-code +
  double-opt-in — the *same* primitive, a second use), ADR-0041 (FDA device-status / RTM gating),
  ADR-0027/0031 (retention / right-of-access / deletion), ADR-0039 (60+ accessibility),
  `docs/product/reimbursement-signoff-packet.md` (D1/D2).

> **Non-diagnostic, consent-first, PHI-heavy.** Enrollment moves real identity data (name, DOB,
> **Medicare Beneficiary Identifier / MBI**) — one of the 18 HIPAA identifiers — so every flow here
> is gated on the executed Microsoft BAA and the §"Privacy / PHI" controls. Ordering never bypasses
> consent. The product remains non-diagnostic; enrollment is administrative, not clinical.

## Context

Today's clinician link (ADR-0005/0012) only connects a patient who **already has an account**
(`invite_patient` matches an existing patient email → pending connection → patient grants consent).
There is **no first-touch acquisition flow** for a brand-new patient — the exact on-ramp the
"clinician as sales force" thesis needs. Separately, BioMech identifies patients by **name + DOB +
Medicare number**, which is the natural deterministic key to (a) enroll the patient and (b)
auto-attach their BioMech gait/balance assessments to the right record — far more reliable than
email for a 60+ population.

This ADR adds the enrollment on-ramp, modeled on the proven **RPM/DME playbook**
(order → ship → activate → follow-up), on top of the existing consent machinery.

### Division of labor (who does what)

- **BioMech** owns the **device and the physical fulfillment** — manufacturing, shipping, and the
  device's own regulatory status. We neither make nor ship hardware.
- **We (AHWG's platform)** are the **software layer that assists care, collects the data, and
  improves results** — order *intake*, the enrollment token + activation, data collection and the
  identity match, the trajectory / Visit-Ready Summary / caregiver surfaces, and the office
  follow-up dashboard.
- Consequence for this ADR: the "ship" step is **BioMech's**; our footprint is the order *ingest*,
  the activation/claim, the data attach, and the follow-up worklist — **not logistics**.

## Decision

### The enrollment lifecycle
1. **Order.** A clinician places an order (in-app, or via BioMech's ordering path relayed to us),
   creating a **pending enrollment** keyed on `name + DOB + MBI`, with **consent captured at the
   visit** (the order carries a consent attestation; app activation reconfirms — double opt-in).
   The order mints an **enrollment token** (a short code + QR + link), all encoding the same
   opaque token, never the MBI.
2. **Ship.** A fulfillment package (BioMech device + welcome letter + enrollment card, all bearing
   the same code) is sent. **Physical fulfillment stays with BioMech/the clinic**; the app owns the
   order, the token, and status tracking — not logistics.
3. **Activate.** The patient uses the code from **any** touchpoint — in-office handout, mailed
   letter, or the follow-up call — landing on a sign-up **pre-linked to the ordering clinic**. They
   confirm identity (must match the ordered `name + DOB + MBI` record) and **claim the record**;
   the pending `ClinicConnection` (`initiated_by = clinic`) activates on the patient's confirmation.
4. **Follow-up.** The office works an **activation dashboard** (below) to chase stalled patients.

### Identity & matching (name + DOB + MBI)
- The enrollment record is keyed on **normalized name + DOB + MBI**, which is also the **join key
  that attaches BioMech assessments** to the right patient (§"Two-layer" below).
- **Match on a token, not the raw number.** Store a **salted hash of `(normalized_name, dob, mbi)`**
  as the match key so BioMech records and app accounts join without the raw MBI being a primary key.
- **Exact match on all three** required to claim; a partial/fuzzy match never auto-links (wrong-match
  = the wrong person's PHI). Patient confirmation (double opt-in) is mandatory before data attaches.

### "Claim your record" & multi-channel activation
- The clinician's order pre-creates a **shell patient record** (identity + pending connection +
  pending BioMech attachment). Activation from any channel resolves the same token → the patient
  claims the shell. One code, three touchpoints, no divergence.

### Consent
- Consent is **captured at the order** (attestation) and **reconfirmed at activation** (the patient's
  explicit share grant, ADR-0012 `grant_consent`). The order does not itself open data flow — the
  existing rule holds: no data reaches the clinic until `status == active` AND the patient's
  `share_with_clinic` is on. Revocation stays instant and never blockable.

### The office activation dashboard (the piece that makes multi-touch convert)
- A clinic-side worklist showing each ordered patient's state: **Ordered → Shipped → Activated →
  Stalled** (e.g., shipped but not activated in N days). This is what lets staff make the
  "did you set up the app?" call; without it, mailed letters die in a drawer. PHI-minimized (names +
  status; never the MBI). Gated by the same clinic authorization as the panel.

### Two layers: enrolled vs app-activated
- Because BioMech data matches on `name + DOB + MBI`, a patient's **gait/balance record can populate
  on the clinician's order even if the patient never opens the app** — the clinician still gets
  value. The **patient app is an additive layer** (check-ins, caregiver, the trend), not a gate on
  the data flowing. This serves the least tech-savvy patients and de-risks activation.

### Reimbursement tie-in (gated, honest)
- **Our role is the RTM monitoring / data-management software** (the treatment-management side), not
  the device supply — **BioMech's device is the device-supply element.** We are neither the biller
  (the clinic bills) nor the device supplier (BioMech is); we assist care, collect the data, and
  evidence the monitoring. This stays **behind D1 (certified coder + counsel) and D2 (FDA device)**
  (ADR-0041); the enrollment machinery is worth building regardless — it is the on-ramp either way.

## Privacy / PHI (the Medicare number raises the bar)

Holding a real **MBI makes the record unambiguously PHI** and triggers the HIPAA hardening this ADR
is paired with. Controls:
- **Minimize the raw MBI.** Prefer the salted-hash match token as the working key. If the raw MBI
  must be retained (e.g., future RTM billing evidence), store it **encrypted at rest** (the Fernet
  vault used for EMR tokens, ADR-0017), **capability-gated**, **never logged, never in audit detail,
  never displayed beyond a last-4** if ever shown.
- **Access & audit.** Every read of identity data is capability-gated and audited (counts/refs,
  PHI-free — ADR-0021). The activation dashboard shows status, not identifiers.
- **Consent & correction.** Right-of-access / correction / deletion (ADR-0027/0031) extend to the
  enrollment identity record; a mis-matched claim is correctable and auditable.
- **BAA gate.** Real name/DOB/MBI flows only after the executed Microsoft BAA; staging/tests use
  **synthetic MBIs** (same posture as all data today).
- **Non-enumeration.** Enrollment lookups and claim attempts must not reveal whether a given
  identity is on file (mirror `invite_patient`'s equalized, rate-limited, non-enumerating design).

## Consequences

- **Unlocks the growth engine** — the clinician on-ramp the "sales force" thesis requires, on the
  proven RPM/DME order→ship→activate→follow-up shape.
- **Solves BioMech data linkage** — name/DOB/MBI is the deterministic join key, so assessments land
  on the right record automatically, no email reconciliation.
- **Cheap on the consent side** (reuses `ClinicConnection` + the invite-by-code primitive shared with
  ADR-0047), but **raises the compliance bar** (real MBI = PHI) — hence the paired HIPAA hardening.
- **Two-layer model** lets the least tech-savvy patients still generate clinician value.

## Alternatives considered

- **Email-only invite (today's flow).** Rejected as the *sole* path — assumes an existing account and
  a reliable email; both fail for the target population. Kept as one activation channel.
- **Store the raw MBI as the primary match key.** Rejected — maximizes raw-PHI exposure; the salted
  hash joins just as deterministically with far less at-rest sensitivity.
- **Require patient app activation for any data flow.** Rejected — excludes the least tech-savvy
  patients and kills clinician value; the two-layer model is strictly better.
- **App owns physical fulfillment.** Rejected — shipping stays with BioMech/the clinic; the app owns
  the order, token, and tracking only.

## Security hardening amendments (2026-07-20 HIPAA assessment)

The 2026-07-20 HIPAA readiness assessment found that several items above, as first written, would
bake in reversible-PHI or impermissible-disclosure risk. These amendments **supersede** the
corresponding text and are **build gates** (see `docs/compliance/real-phi-readiness-plan.md §4`).
The whole flow stays synthetic until the **BioMech BAA** is executed.

1. **Match token = keyed HMAC, not a plain salted hash.** An 11-char fixed-format MBI with a
   deterministic salt is brute-forceable — a plain hash is **still PHI**, not de-identification.
   Use HMAC-SHA256 (or Argon2id + fixed pepper) with the **pepper in the vault/KMS, never in DB or
   code**; treat the token as PHI (access/audit/encryption apply).
2. **No clinical data binds before confirmation.** BioMech gait/balance data must **not** attach to a
   shell on the order alone; attach is gated on the **patient claim** (or explicit clinic
   verification). A mis-keyed MBI must never silently bind one patient's PHI to another. Publish the
   name-normalization algorithm; a non-unique/conflicting triple → **manual review**; wrong-match
   correction/merge is a **specified, audited, reversible** flow (reusing `revises_id` /
   `entered_in_error`), not deferred.
3. **Consent is a §164.508 authorization, modeled explicitly.** Add an **append-only, versioned
   `EnrollmentAuthorization`** (attesting principal, timestamp, instrument + version, scope); order
   creation requires it; pre-activation revocation → **shell purge + BioMech detach**; disclosures
   accountable under §164.528.
4. **Claim is bound to the enrollment token, not a standalone name+DOB+MBI lookup** (which would be an
   enumeration + MBI-validation oracle). Require **token possession**; verify the triple only within
   token scope; per-token + per-IP caps, equalized responses, lockout + audit.
5. **Least-privilege, separately-audited identity reads** — a distinct capability key + a distinct
   `read_identity` audit action (refs/counts only, never the MBI); the activation dashboard renders
   **status only**.
6. **`SECRET_STORE_KEY` co-required with this feature** — the config validator **enforces** the vault
   key when the enrollment flag is on (fail closed, never plaintext); **MultiFernet** rotation since
   the MBI is long-lived.
7. **Erasure + export cover the identity store** — add it to the FK-safe deletion order; purge the
   encrypted MBI via `SecretStore.delete`; include in `/me/export`; test zero residual.
8. **No "last-4" MBI display** — last-4 beside name + DOB is still an identifier; show none.
9. **Hash-only until D1** — no raw MBI at rest until the reimbursement path is unblocked (feature flag)
   — resolves open question #3 toward least-necessary.
10. **Unclaimed-shell retention/purge** — a stalled-shell window with automated MBI purge, plus an
    audited ops/clinic administrative correct-and-delete for non-app subjects.

## Open questions (for the owner / reviewers)

1. **Order origin** — orders placed in-app by the clinic, or received from BioMech's ordering system
   (an inbound integration)? Determines whether we build an order-entry UI or an order-ingest API.
2. **Consent instrument** — what the at-visit consent attestation is (paper signed + attested in the
   order, or an e-consent), and how it's evidenced for a future audit.
3. **MBI retention** — do we retain the raw encrypted MBI at all pre-D1, or hold only the hash until
   the reimbursement path is unblocked? (Least-PHI default: hash-only until needed.)
4. **Stalled threshold & follow-up cadence** for the dashboard, and whether follow-up nudges are
   manual (staff) or system-assisted.
5. **Wrong-match handling** — the correction/merge flow when a claim matches the wrong shell.
6. **Fulfillment status source** — how "Shipped" is known (BioMech ships; do they post back a status,
   or is it manually marked?).
