# ADR-0005: Connection Modes — Self-Connected & Clinical

**Date:** 2026-07-11
**Status:** Accepted (owner decision)

## Context

The product ships in two versions (requirements v1/v1.1). The owner defined the way an
account comes online as **two connection modes**:

1. **Self-connected** — the patient sets up and owns their account, connects their own
   data sources (BioMech data, labs, ADL), and self-manages. No clinic involved. This
   is the B2C experience.
2. **Clinical connecting** — the patient is linked to a **servicing clinic**. A
   clinician configures which monitoring is active (order-like), and the patient's data
   is transmitted to that clinic. This is the clinical experience.

The same app, backend, and capability model serve both; connection mode determines
**toggle authority**, **tenancy**, **consent**, and **data routing**.

## Decision

Make **connection mode a first-class property of the account**, not something inferred.

- `Patient.connection_mode ∈ { self_connected, clinical }`, default `self_connected`.
- A **`ClinicConnection`** record represents a clinical link: which clinic, status,
  who initiated it, when consent was granted, when revoked.
- **A clinical connection may be established two ways:**
  - **Clinic-initiated** — the clinic invites/creates the patient (their staff already
    work in an order-driven portal; this matches that flow).
  - **Patient-initiated** — the patient enters a clinic link code / selects their
    provider to request the connection.
- **Consent gates data flow.** No patient data flows to a clinic until
  `consent_granted_at` is set on an **active** `ClinicConnection`. A clinician toggling
  a capability on cannot start transmission before consent exists (HIPAA; ADR-0003).
- **Revocable.** The patient can revoke a clinical connection at any time; revocation
  stops data flow and is audit-logged. (Records already shared follow the clinic's
  retention obligations — a legal/ADR detail, not an app toggle.)
- **Upgrade path.** A self-connected patient can later connect to a clinic (mode
  self_connected → clinical) without losing their history — their existing longitudinal
  record simply becomes visible to the clinic from the consent point forward (exact
  back-sharing window is a consent-design decision).

## How mode changes behavior

| Concern | Self-connected | Clinical |
|---|---|---|
| Toggle authority | Patient controls activation | Clinician controls activation (order-like, with expiry/renewal); patient retains a participation veto |
| Tenancy | Self-owned; no clinic scope | Scoped to the connected clinic; every clinical query filters by clinic |
| Consent | Implicit for own use | Explicit, recorded, revocable before any clinic data flow |
| Data routing | Stays with the patient | Transmitted to the servicing clinic |
| Legal posture | FTC/state privacy | We are a Business Associate of the clinic (BAA) |

## Consequences

- **Data model:** add `connection_mode` to `Patient` and a `ClinicConnection` model
  (status: pending → active → revoked; `initiated_by`; `consent_granted_at`;
  `revoked_at`). `Patient.clinic_id` mirrors the currently-active clinical connection
  for fast tenancy filtering.
- **Capabilities:** the existing `PatientCapability.set_by` authority (patient vs
  clinician) is chosen by connection mode; the server enforces that a clinician can
  only set toggles for patients clinically connected to that clinician's clinic.
- **Onboarding UX:** first run asks "How do you want to connect?" — on your own, or
  with your clinic. (Mockup added.)
- **Audit:** connection create/consent/revoke are audit events like any config change.

## Options considered

- **Infer mode from `clinic_id` null/not-null (status quo skeleton):** rejected — too
  implicit; can't represent pending/revoked, initiator, or consent state.
- **Two separate apps/accounts:** rejected — duplicates everything and breaks the
  self→clinical upgrade path.
- **Explicit connection_mode + ClinicConnection record:** chosen — models the real
  lifecycle (invite, consent, revoke, upgrade) and keeps one account.
