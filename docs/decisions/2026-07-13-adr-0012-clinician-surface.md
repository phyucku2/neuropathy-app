# ADR-0012: Clinician Surface

**Date:** 2026-07-13
**Status:** Accepted
**Builds on:** ADR-0005 (connection modes & consent gating), ADR-0010 (auth roles;
clinicians are provisioned, not self-registered) and ADR-0011 (deterministic-first
narration).

## Context

The clinical version needs its first server-side surface: clinicians reviewing the
patients connected to their clinic (mockups/clinician-app.html). ADR-0005 already
defined the `ClinicConnection` lifecycle and the hard rule that **consent, not a
clinician toggle, gates data flow** — but no clinic entity, no clinician accounts, and
no clinician endpoints existed. Every design choice here is a privacy choice: a
clinician surface is exactly where cross-patient and cross-clinic leaks would happen.

## Decision

A `Clinic` model plus a clinician router, with five postures:

1. **One consent gate.** `may_transmit_to_clinic` (app/services/connection.py) is THE
   predicate for every clinician read — panel membership and the per-patient access
   check both call it, never a re-derived copy. `ClinicConnection.clinic_id` becomes a
   real foreign key to the new `clinic` table, and clinician users carry
   `app_user.clinic_id` so every clinical query is clinic-scoped (ADR-0005 tenancy).
2. **404 over 403.** Any `/clinic/patients/{id}/*` request the clinic may not serve —
   cross-clinic, non-consented, revoked, or nonexistent — answers 404. A clinician
   must not be able to distinguish "not my patient" from "no such patient" (no
   existence leak). 403 is reserved for role failures (`require_clinician`, mirroring
   `require_patient`).
3. **Deterministic-only clinician trajectory.** The clinician view reuses the shared
   trajectory computation (app/services/trajectory.py — the same helper the patient
   endpoint calls, so the two can never drift) and NEVER invokes the AI narrator;
   `narrative_source` stays `deterministic`. ADR-0011's narration is a warmth layer
   for the patient's own view; clinicians get the computed facts.
4. **Non-enumerating invitations.** `POST /clinic/invitations` answers a
   byte-identical 202 whether or not the email matches a patient account; a match
   creates a pending, clinic-initiated connection that only patient consent
   activates. The clinician surface must not become an account-probing oracle.
   Query work is equalized across the matched/unmatched branches so steady-state
   response timing does not reveal a match either; the one-time INSERT on a first
   successful invite remains a residual single-shot timing signal (adversarial
   review), accepted because it cannot be sampled repeatedly — full elimination
   would require queueing invitations off-request and is deferred with rate
   limiting to the hardening pass.
5. **One live connection per patient-clinic pair — enforced in storage.** The invite
   flow's check-then-insert cannot hold under concurrent requests (adversarial
   review: duplicate connections would let a clinic keep reading after the patient
   revoked "the" connection). A partial unique index
   (`uq_clinic_connection_live` on `(patient_id, clinic_id) WHERE status !=
   'revoked'`) backstops it; both repository implementations raise
   `DuplicateLiveConnectionError`, which the invite absorbs (identical 202, audit
   records `created=false`). Revoked rows leave the index, so patients can
   reconnect.
6. **Clinician-actor audit.** Every clinician read of patient data writes an audit
   event with the clinician as actor and the patient as subject (counts and
   references only, never values — CLAUDE.md §5); invitations, consent grants, and
   revocations are audited too. Clinician provisioning is ops-gated: a
   settings-provided `OPS_BOOTSTRAP_TOKEN` guards `POST /clinic/clinicians` and the
   endpoint fails closed (403) when the token is unconfigured — an interim gate until
   a dedicated ops-auth surface exists (ADR-0010 follow-up).

## Consequences

- Data model: new `clinic` table; `app_user.clinic_id` FK; `clinic_connection.clinic_id`
  FK; `uq_clinic_connection_live` partial unique index (migration 0002). The
  migration backfills placeholder clinic rows for any pre-existing
  `clinic_connection.clinic_id` values and revokes duplicate live connections
  (keeping the oldest) before its constraints land, so populated dev/staging
  databases upgrade cleanly; its downgrade refuses while `clinic_connection` rows
  exist rather than orphaning consent records and bricking re-upgrade (adversarial
  review). `CurrentUser` and `UserRecord` gain a defaulted trailing `clinic_id`, so
  existing constructions are untouched.
- A clinic founded by a provisioning request that then fails (e.g. duplicate email)
  is rolled back in both storage modes — Postgres via the request transaction,
  in-memory via explicit `ClinicRepository.delete` — so retries never accumulate
  same-name orphan clinics (adversarial review).
- `Patient.clinic_id` / `connection_mode` are explicitly documented as RESERVED and
  unmaintained: `ClinicConnection` + `may_transmit_to_clinic` are the sole source of
  truth for clinic linkage; a mirror would be a dual-write to keep consistent, and
  nothing reads it yet (adversarial review).
- Endpoints: `/clinic/clinicians`, `/clinic/invitations`, `/clinic/patients`,
  `/clinic/patients/{id}/trajectory|observations`; patient-side `/connections` list,
  `/connections/{id}/consent`, and `DELETE /connections/{id}` (idempotent revoke).
- Config: `ops_bootstrap_token` (new, default unset = provisioning disabled). No
  secrets in the repo.
- Tests cover: the consent lifecycle, consented-only panel, cross-clinic and
  non-consented 404s, non-enumeration (byte-identical bodies), deterministic-only
  trajectory, audit trail, and the fail-closed bootstrap gate.

## Options considered

- **403 for cross-clinic access:** rejected — a 403 confirms the patient id exists;
  404 keeps unauthorized ids indistinguishable from unknown ones.
- **Re-checking consent in each route with ad-hoc status logic:** rejected — a second
  implementation of the ADR-0005 invariant would eventually drift; one unit-locked
  predicate is the gate everywhere.
- **Invitation responses that report "no such patient":** rejected — friendlier UX,
  but turns the endpoint into an email oracle for anyone holding a clinician token.
- **AI narrative on the clinician view:** rejected for now — clinicians need sourced,
  computed facts (mockup shows the signal table); narration is patient-facing scope
  (ADR-0011) and would double the BAA-gated disclosure surface.
- **Self-registration for clinicians / no gate:** rejected — ADR-0010 says provisioned
  only; a fail-closed bootstrap token is the smallest honest interim gate.
