# ADR-0020: Feature-Toggle Enforcement Wiring (the last three keys)

**Date:** 2026-07-14
**Status:** Accepted
**Builds on:** ADR-0013 (feature toggles: registry, effective-state predicate, authority
rule, the `enforced` flag, the `require_capability` seam), ADR-0011 (AI narrative BAA
gate), ADR-0012 (clinician surface consent gate + 404-over-403 existence privacy),
ADR-0005 (consent, not a clinician toggle, gates data flow), ADR-0008/0009 (EMR
connect/callback/pull/revoke).

## Context

ADR-0013 shipped the toggles surface with three keys registered but **`enforced=False`**
— visible and read-only, refusing writes with 409 "not changeable yet", because a
stored "off" that the feature ignores is a false promise about what is processed or
disclosed. ADR-0013 deliberately deferred wiring their consumers: *"`emr_connect`
gating of the connect flow, `ai_narrative` gating of the narrator, and
`share_with_clinic` gating of clinician reads are the follow-ups — each needs its own
interaction decision with existing gates before adoption."* This ADR makes those three
decisions, flips each key to `enforced=True`, and wires it to exactly one consumer.

The hard part is not the flip; it is how each toggle **composes with a gate that
already exists** — the EMR pull's `ingest_labs` gate, the narrator's BAA gate, and the
clinician surface's `may_transmit_to_clinic` consent gate — and, for
`share_with_clinic`, how it composes with ADR-0013's own **toggle-authority rule**.

## Decision

### 1. `emr_connect` gates ESTABLISHING/REFRESHING a connection — the connect-vs-pull split

`require_capability("emr_connect")` is applied to **`POST /emr/connect`** and
**`GET /emr/callback`** (both patient-scoped; the callback is the connection-establishing
step of the same handshake, so gating connect without the callback would be a half-gate).
A patient turning `emr_connect` off therefore prevents **new** EMR connections and the
completion of an in-flight one — a 409 at the seam, mirroring `POST /adl`/`POST /labs`.

Deliberately **NOT** gated by `emr_connect`:

- **`DELETE /emr/connections/{id}` (revoke).** Revocation must never be toggle-blockable
  — turning a toggle off can never trap a patient in a connection. This is the same
  hard rule the EMR pull precedent already documents (`ingest_labs` gates the pull but
  not revoke) and it is absolute.
- **`POST /emr/connections/{id}/pull` (the data write).** The pull is already
  `ingest_labs`-gated (ADR-0013: the pull writes lab Observations, the same data class
  as `POST /labs`). We keep that gate and do **not** add `emr_connect` on top. The split
  is intentional and documented: **`emr_connect` = "may I open/refresh a pipe to the
  EMR", `ingest_labs` = "may that pipe write labs into my record."** They are
  independent controls: a patient can stop importing labs while leaving the connection
  live (revoke later), or stop making new connections while an existing one keeps
  syncing. Folding pull under `emr_connect` would conflate "stop connecting" with "stop
  importing" and silently strip the patient of one of the two.

### 2. `ai_narrative` ANDs with the BAA gate — an in-handler branch, never a 409

`ai_narrative` gates **narrator scheduling in `GET /trajectory`**. The rule is a logical
**AND** with the existing BAA gate (ADR-0011): the LLM path runs only when **toggle ON
AND BAA confirmed AND a narrator is configured**. Any one off (`ai_narrative` off, OR
BAA not confirmed, OR no narrator) ⇒ the endpoint stays **fully deterministic**
(`narrative_source` = `"deterministic"`).

Crucially this is **not** a `require_capability` 409 gate. `GET /trajectory` must always
return 200 with the deterministic summary — the toggle governs an *enhancement*, not
access to the view. So it is an **in-handler branch** that, when the toggle is off:

- does **not** serve a cached AI narrative (even if one exists for the identical
  computed trajectory), and
- does **not** schedule the background narration.

Because ADR-0011 makes *scheduling* the disclosure (the `ai_narrative` audit event fires
in the request that schedules, so error/rejection paths are never unaccounted), and
scheduling never happens when the toggle is off, **no AI-disclosure audit is written**
when the patient has `ai_narrative` off. The toggle is read only when a narrator is
configured, so the deterministic path costs nothing extra. `ai_narrative` follows the
normal ADR-0013 authority rule (clinician-controlled while the patient is clinically
managed) — no carve-out; the patient-held carve-out below is unique to
`share_with_clinic`.

### 3. `share_with_clinic` — a patient-held CONSENT control gating clinician reads

`share_with_clinic` is an **additional gate on top of** the ClinicConnection consent
(`may_transmit_to_clinic`) for every clinician read of a patient's data. Two decisions
make it safe and non-drifting:

**(a) One predicate, three call sites.** `ClinicService._may_read_patient(connection)`
is the single gate: it **ANDs** `may_transmit_to_clinic(connection)` (ADR-0005 consent)
with `share_with_clinic_effective(patient)` (the patient's toggle, judged by ADR-0013's
unit-locked `is_effectively_active` + the registry default). Both `panel()` and
`connection_for_clinician()` route through it, and every per-patient clinician read
(`/clinic/patients/{id}/trajectory|observations|capabilities`) and every clinician
capability **write** goes through `connection_for_clinician`/`_consented_connection`.
So when a patient turns `share_with_clinic` off:

- they **drop off every clinician's panel**;
- every `/clinic/patients/{id}/*` read answers **404 "Patient not found"** — the SAME
  neutral answer as a cross-clinic or non-consented patient (ADR-0012 404-over-403
  existence privacy; a denial must not reveal that the patient exists or why access
  failed);
- clinician capability writes for that patient are refused the same neutral **404**.

Because it is one predicate, the panel, the reads, and the writes can never diverge — a
patient can't be off one surface but readable on another. `share_with_clinic_effective`
is **read-only** (no lazy row seeding), so a clinician read can never mutate capability
state. Default is **True** (sharing on), so existing consented connections keep working
with no back-fill — back-compat by construction.

**(b) The patient-held-consent carve-out from clinician toggle-authority.** ADR-0013's
authority rule gives a *clinically-managed* patient's toggles to the clinician (order-
style). That rule must **NOT** extend to `share_with_clinic`, because this key is the
patient's own *mechanism to stop sharing*. A clinic controlling the patient's ability to
stop sharing would be perverse — the consent control would be owned by the party it
exists to restrain. So `share_with_clinic` is **patient-settable regardless of
clinically-managed status** (the `ClinicallyManagedError` refusal is skipped for it, and
only for it; the FOR SHARE race-lock still guards every other key). Symmetrically, a
**clinician can never set** `share_with_clinic` (even for a consented patient in the
narrow window before they turn it off): `set_for_clinician` raises
`PatientHeldCapabilityError` (409). And `managed_by` for this key always reads
`"patient"` in `GET /capabilities` — even while managed — so the client renders it as an
interactive, patient-owned control rather than a clinic-managed read-only row. Every
other key is unchanged.

Revoking share is an **auditable consent change** (`set_capability`, actor = patient) —
and the clinician-facing denial leaks nothing (a bare 404).

## The `enforced` flag lives on

All six shipped keys are now `enforced=True`. The `enforced` mechanism and its read-only
rendering (patient "Coming soon" pill, clinician "Not wired yet" pill) are **retained**
for any FUTURE key introduced un-wired — the ADR-0013 pattern (register visible, flip on
wiring) still holds. The service still refuses writes to an un-wired key for both actors
(`CapabilityNotEnforcedError`), unit-tested with a synthetic future key.

## Consequences

- `capability.py`: three keys flipped to `enforced=True`;
  `SHARE_WITH_CLINIC_KEY`, `managed_by_for`, `share_with_clinic_effective`,
  `PatientHeldCapabilityError` added; `set_for_patient` skips the managed-authority
  refusal for `share_with_clinic`; `set_for_clinician` refuses it.
- `clinic.py`: `ClinicService` gains `capabilities` + `patient_capabilities` repos and
  the `_may_read_patient` predicate; `panel()` and `connection_for_clinician()` gate on
  it. `deps.py` shares the capability stores between the clinic and capability services
  in both storage modes, so the read gate always sees the patient's live toggle.
- `emr.py`: `emr_connect` gate on connect + callback. `trajectory.py`: `ai_narrative`
  in-handler AND-branch.
- No schema/migration change (the Capability/PatientCapability tables are from 0001).
- Frontend: none functionally — the SPA reads `enforced` from the API, so the three keys
  render interactive automatically. The msw fixtures were updated to reflect the new
  `enforced=True` reality, and the two read-only-rendering tests now exercise a synthetic
  future un-wired key (the defensive path is preserved).

## Options considered

- **Fold the EMR pull under `emr_connect` too:** rejected — conflates "stop connecting"
  with "stop importing"; the two are independent patient controls and `ingest_labs`
  already governs the write.
- **Make `ai_narrative` a `require_capability` 409 gate:** rejected — `GET /trajectory`
  must always return 200; the toggle governs an enhancement, not access. In-handler
  branch keeps the deterministic response whole.
- **Let clinicians control `share_with_clinic` when managed (uniform authority):**
  rejected — perverse; a consent-to-share control the clinic could disable is not a
  consent control. The carve-out is the whole point.
- **403 (or a descriptive body) when `share_with_clinic` is off:** rejected — a 403 or
  "sharing disabled" message confirms the patient exists and leaks the reason; 404
  keeps a share-revoked patient indistinguishable from a non-consented or nonexistent
  one (ADR-0012).
- **Two separate predicates for panel vs. per-patient reads:** rejected — they would
  drift; one `_may_read_patient` is the gate everywhere.
