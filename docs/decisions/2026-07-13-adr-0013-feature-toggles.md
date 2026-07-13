# ADR-0013: Feature Toggles — Server-Enforced Capability Authority

**Date:** 2026-07-13
**Status:** Accepted
**Builds on:** ADR-0005 (connection modes; toggle authority follows connection mode)
and ADR-0012 (consent gate, 404-over-403 posture, clinician-actor audit).

## Context

The Capability/PatientCapability tables have existed since migration 0001, but no
endpoint exposed them: nothing let a B2C patient turn a feature off, nothing let a
clinician configure a clinical patient's monitoring order-style, and no feature
endpoint asked whether it was allowed to run. ADR-0005 already fixed the product
rule — B2C patients control their own toggles; clinical patients' toggles are
clinician-controlled with optional expiry, renewable like an order — and made clear
the enforcement must be server-side: client toggles are UI hints, never authority.
The open questions were what "on" means, who may flip it, and how features consume
the answer without breaking everything that already works.

## Decision

A code-registry + lazy rows + one effective-state predicate, with five postures:

1. **The registry lives in code; rows are seeded lazily.** `CAPABILITIES`
   (app/services/capability.py) is the canonical list of what the app ships today —
   `ingest_labs`, `ingest_adl`, `ingest_biomech`, `emr_connect`, `ai_narrative`,
   `share_with_clinic` — each with key, name, and default. (`ingest_biomech` was added
   with the BioMech PDF ingest module, ADR-0014, `enforced=True`; its consumer is
   `POST /biomech/reports`.) Registry DB rows are get-or-created by key on
   first touch (race-safe: the unique key constraint backstops it and the loser
   re-fetches the winner's row, mirroring the ADR-0012 duplicate-invite absorption),
   so both storage modes work without seed scripts and a deploy can never "forget"
   a capability. No new migration: the tables are from 0001.
2. **One effective-state predicate.** `is_effectively_active` (pure, unit-locked,
   like `may_transmit_to_clinic`): effective = `capability.available` AND
   (`row.active` if a row exists, else the registry default) AND (row not expired:
   `expires_at` is None or `> now`). **Absence of a row means the default** — every
   default is True, so every account that never touched a toggle behaves exactly as
   before this ADR (back-compat by construction). The ops kill switch
   (`available=False`) overrides everything, including explicit grants.
3. **The authority rule, server-enforced.** A patient is *clinically managed* iff at
   least one of their ClinicConnections currently passes `may_transmit_to_clinic` —
   reused, never re-derived; `Patient.clinic_id`/`connection_mode` stay RESERVED
   (ADR-0012). Clinically managed: only a clinician from a consented clinic (or ops,
   later) may change toggles; the patient's own PUT answers 409 with a clear reason
   naming the way out (ask the care team, or revoke the connection). Not managed
   (B2C): the patient controls their own toggles. Revocation flips authority back to
   the patient instantly — the clinician's last-set rows keep their state until the
   patient, back in authority, changes them. `set_by` records the actor on every row;
   `expires_at` is settable ONLY by clinicians (order-style, renewable by re-issuing;
   an expired grant is off until renewed). The patient schema simply has no expiry
   field, so it cannot be smuggled.
4. **Clinician surface = the ADR-0012 postures verbatim.**
   `/clinic/patients/{id}/capabilities[/{key}]` uses the same `_consented_connection`
   gate as every other clinician view: cross-clinic, non-consented, revoked, and
   nonexistent patients are all 404. The service re-judges the handed-in connection
   with `may_transmit_to_clinic` (defense in depth, like the panel) and the route
   maps that refusal to the same 404. Status codes on writes: unknown key -> 404
   (not part of the product's registry); capability killed by ops -> **409**, not
   404 — the registry is public in the patient's own GET, so a 404 would hide
   nothing, and 409 tells the truth: the key exists but the state conflicts with
   the request.
5. **Changes are audited; reads are not.** Every toggle change writes an AuditEvent
   (actor, action=`set_capability`, patient as subject, detail = key/active/
   expires_at/set_by and the consented connection id for clinician writes — never
   health-data values). Toggle **reads** are consent-gated but deliberately NOT
   audited: toggle state is configuration, not PHI — auditing every GET would bury
   the genuine PHI-access trail (panel/trajectory/observations reads, which remain
   audited per ADR-0012) in noise. If toggle state is ever folded into a patient-
   facing access report, revisit this choice.

**Enforcement seam.** `require_capability(key)` (app/api/deps.py) is a route
dependency that answers 409 "This feature is turned off" when the capability is
effectively off for the authenticated patient. Consumers: `POST /adl`
(`ingest_adl`), `POST /labs` and `POST /emr/connections/{id}/pull` (both
`ingest_labs` — the pull writes lab Observations, the same data class as the upload,
so one toggle governs both writers; adversarial review found the ungated pull would
have defeated a clinician's `ingest_labs=off` order and the kill switch).
Deliberately NOT wired in this PR: auth, connections (revocation must never be
blockable by a toggle — including EMR revoke), trajectory reads (`emr_connect`
gating of the connect flow itself, `ai_narrative` gating of the narrator, and
`share_with_clinic` gating of clinician reads are the follow-ups — each needs its
own interaction decision with existing gates before adoption).

**Unwired toggles are read-only (`enforced` flag).** A settable toggle whose feature
ignores it is a false promise — a patient who switched `ai_narrative` off while the
narrator kept running would be misled about what is processed and disclosed
(adversarial review, high). Each `CapabilitySpec` therefore carries `enforced`;
writes to `enforced=False` keys (`emr_connect`, `ai_narrative`,
`share_with_clinic`) answer 409 "not changeable yet" for patients AND clinicians,
and the flag is exposed in `GET /capabilities` so clients render them read-only.
Each key flips to `enforced=True` in the PR that wires its consumer.

**Expiry pairs only with enable.** `active=false` + `expires_at` would read as
"suspended until <date>" but expiry only ever deactivates — the schema refuses the
combination (422) instead of storing a false promise (adversarial review).

**Authority check is race-free in Postgres.** The patient-write path judges
`is_clinically_managed` with a FOR SHARE read (`list_for_patient(for_share=True)`),
so a toggle write cannot slip past a concurrent consent grant: it either commits
strictly before the consent or sees it and is refused (adversarial review).

## Consequences

- New: CapabilityRepository + PatientCapabilityRepository (Protocol + in-memory +
  Postgres twins; `upsert` is insert-first and absorbs `uq_patient_capability` via a
  savepoint, mirroring `PostgresClinicConnectionRepository.add`, so one row per
  (patient, capability) survives even under concurrent writes and the request
  transaction stays usable), CapabilityService, `/capabilities` +
  `/clinic/patients/{id}/capabilities` routes, `get_capability_service` wired in
  both storage modes exactly like the clinic service (in-memory singleton sharing
  the SAME connection/audit stores; Postgres per-request).
- No schema change; migration/model parity untouched.
- B2C patients get real control (off means the server refuses, not that the client
  hides a button); clinical patients see their configuration but cannot change it
  while a consented connection is live.
- The seam adds one capability lookup (two indexed point reads) to each gated write;
  within the write budget.
- Expiry checks always compare against an injected `now`; tests use fixed
  timestamps, never wall-clock-derived assertions (CI-flake rule).

## Options considered

- **Toggle authority from `Patient.connection_mode`:** rejected — the column is
  RESERVED/unmaintained (ADR-0012); deriving authority from consented connections
  reuses the one predicate that is already the source of truth.
- **Seeding capabilities via migration/fixtures:** rejected — a seed can drift from
  the code that enforces it, and the in-memory mode would need a parallel seed path;
  lazy get-or-create keeps one list authoritative everywhere.
- **404 for an ops-killed capability on PUT:** rejected — the key is visibly listed
  in the patient's own GET, so 404 would be a lie that hides nothing; 409 states the
  conflict.
- **Auditing clinician toggle reads:** rejected for now — configuration, not PHI;
  documented above with the revisit trigger.
- **Patient veto field / dual-authority model:** deferred — ADR-0005 mentions a
  participation veto for clinical patients; modeling it needs product input
  (veto vs. revocation is a consent-design question), and revocation already gives
  the patient a hard stop today.
- **Gating every existing endpoint in this PR:** rejected — big-bang adoption risks
  breaking flows whose gate interaction is undecided (e.g. a toggle must never block
  revocation); the seam + two consumers proves the pattern and scopes the change.
