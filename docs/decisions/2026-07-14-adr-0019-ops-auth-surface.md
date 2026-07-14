# ADR-0019: Ops-Auth Surface — Per-Operator Identities Replace the Shared Bootstrap Token

**Date:** 2026-07-14
**Status:** Accepted
**Builds on:** ADR-0010 (application auth — Argon2id, JWT access/refresh, role gates),
ADR-0012 (clinician surface — provisioning is an ops action), and ADR-0017 (the
hardening pass that made the shared bootstrap token constant-time, min-length,
fail-closed, and denial-audited, and explicitly flagged a dedicated ops-auth surface as
the production-readiness follow-up).

## Context

Clinician accounts are provisioned by `POST /clinic/clinicians`, an operator action.
Until now that endpoint was gated by a single shared `OPS_BOOTSTRAP_TOKEN` presented in
an `X-Bootstrap-Token` header. ADR-0017 hardened that gate but named it interim, and the
limits are structural, not fixable by more hardening:

- **No per-operator identity.** Every provisioning action is attributed to the string
  `"ops"` with a fixed sentinel actor id — the audit trail cannot say *which* operator
  provisioned a clinician. For a regulated health system that is a weak accountability
  story (HIPAA/SOC 2 both want named actors).
- **No revocation of one operator.** The secret is shared; you cannot revoke a single
  holder who leaves or is compromised.
- **No rotation without a fleet-wide change.** Rotating the token invalidates it for
  *every* holder at once and requires redeploying the secret to all of them.

The right shape is real ops identities with their own credentials and a scoped role,
authenticating through the existing auth stack — not a shared secret on the request path.

## Decision

### 1. The ops principal is a role on the existing user, not a new table

An operator is an `app_user` row with `role = UserRole.ops`, carrying **neither**
`patient_id` **nor** `clinic_id`. `UserRole.ops` already existed in the enum (and in the
audit `actor_role` vocabulary), so no enum migration is needed.

Chosen over a dedicated `ops_account` table because a role on the user model **reuses the
entire auth stack unchanged**: Argon2id hashing (`app/core/security.py`), the same
`/auth/login` issuing access/refresh JWTs, the same `get_current_user` decode/fetch, the
same refresh flow. A separate table would have duplicated all of it (a second login
endpoint, a second token issuer, a second identity table) for no benefit — an operator is
an authentication identity, exactly what `app_user` already models. The clinician role set
the precedent: a role that carries a clinic but no patient record; ops is the sibling that
carries neither.

### 2. Login and role gate — ops authenticate like everyone else

Operators log in through the **same** `POST /auth/login`; their JWT carries `role=ops`.
`require_ops` (`app/api/deps.py`) is the gate — 403 for any non-ops or deactivated
caller — mirroring `require_clinician`. Because a short-lived access token can outlive a
just-issued deactivation by up to the token TTL, `require_ops` re-checks the `active`
flag from the freshly-fetched user record, not just the role; login is not the only
place revocation bites.

### 3. Provisioning now requires an ops bearer, and records the real actor

`POST /clinic/clinicians` drops the `X-Bootstrap-Token` gate for `require_ops`. The
provisioning audit event's `actor_id` is now the **authenticated operator's user id** —
genuine per-operator attribution, the concrete improvement over the `"ops"`/sentinel
actor. All other postures (404-over-403 elsewhere, orphan-clinic cleanup on a failed
founding, 422 on unknown clinic) are unchanged.

### 4. Bootstrapping the first operator — the chicken-and-egg, resolved

Real ops accounts are created by an authenticated ops — but the first one cannot be. The
`OPS_BOOTSTRAP_TOKEN` survives with its power **narrowed to exactly one endpoint and one
moment**: `POST /ops/accounts`.

- **While zero ops accounts exist**, `POST /ops/accounts` is unauthenticated and gated
  ONLY by `OPS_BOOTSTRAP_TOKEN`, carrying the full ADR-0017 posture verbatim (fail closed
  when unconfigured, constant-time compare, one byte-identical 403 for missing/wrong,
  failed attempts audited as `bootstrap_denied` under the fixed sentinel actor with only
  the failure shape — never token material — and that denial audit **capped by the
  sliding-window limiter** so this one anonymous surface cannot be used to flood the PHI
  audit table). This is now the *only* unauthenticated write surface, which is exactly why
  the denial-audit + rate-limit protection moved here with it.
- **The moment any ops account exists** (checked by `count_with_role(ops) == 0`), that
  path self-closes: `POST /ops/accounts` requires a valid ops bearer (`require_ops`), and
  the bootstrap token opens nothing — presenting it without a bearer is a 401. A
  **deactivated** ops still counts as "exists", so the gate never silently reopens.

This preserves fail-closed end to end: **no token configured + no ops accounts = no ops
can be bootstrapped = no clinician can be provisioned.** The shared secret is off the
steady-state path entirely; it fires at most once in a deployment's life.

### 5. Revocation and rotation — per-operator, which the shared token never had

`POST /ops/accounts/{id}/deactivate` (require_ops) flips an `active` flag and stamps
`disabled_at`. A deactivated operator fails login (same 401 as an unknown email — no
enumeration) and fails `require_ops` immediately. This is per-operator revocation and, by
extension, rotation: stand up a replacement operator, deactivate the old one, and no other
operator is touched. Deactivation is idempotent (a second call is a quiet success with no
second audit event) and **refuses (409) to remove the last active operator** — with the
bootstrap gate closed once any ops exists, removing the last one would lock the
provisioning surface out entirely.

The `active`/`disabled_at` columns live on `app_user` generally (not an ops-only side
table): the flag is a natural account property and login enforces it for every role, so a
compromised account of any role can be disabled — ops is simply the first role that uses
the deactivation *endpoint*.

## Consequences

- **Migration 0005** adds `app_user.active` (boolean, NOT NULL, `server_default true` so
  it lands cleanly over existing rows) and `app_user.disabled_at` (timestamptz, nullable).
  No enum change (`ops` already present). Downgrade drops both columns — it forfeits only
  activation state, never an account or its credentials, so unlike migration 0002 there is
  nothing to refuse over. Models updated so autogenerate parity holds.
- **New surface:** `app/api/routes/ops.py` (`POST /ops/accounts`, `POST
  /ops/accounts/{id}/deactivate`), `app/schemas/ops.py`, `require_ops`/`OpsUserDep` in
  deps, and `AuthService.create_ops` / `ops_account_exists` / `active_ops_count` /
  `deactivate_ops`. The `UserRepository` gains `count_with_role` and `set_active`
  (in-memory + Postgres).
- **Config/docs:** `OPS_BOOTSTRAP_TOKEN`'s documented role narrows to first-ops bootstrap
  in `config.py` and both `.env.example` files. The validators (min-length, never-echo)
  are unchanged.
- **Auditing:** new actions `create_ops` (actor = the creating operator, or null with
  `bootstrap: true` for the first-ops creation) and `deactivate_ops` (actor = the acting
  operator). `create_clinician` now records the real operator. `bootstrap_denied` keeps
  its meaning but is now emitted by the first-ops surface.
- **Compatibility:** the `X-Bootstrap-Token` path on `POST /clinic/clinicians` is gone —
  a purely operator-facing break with no patient/clinician impact. The frontend never
  called `/clinic/clinicians` (provisioning is a back-office action, not a UI screen), so
  no frontend change is required. Operational rollout: deploy, `POST /ops/accounts` once
  with the bootstrap token to mint the first operator, then provision through ops bearers;
  the bootstrap token can be retired from the environment after that first call.

## Options considered

- **A dedicated `ops_account` table + separate ops login/JWT:** rejected — duplicates the
  whole ADR-0010 auth stack (hashing, login, token issue/verify, identity table) for a
  principal that is just an authentication identity. A role on `app_user` reuses all of it.
- **Keep the shared token, just rotate it more often:** rejected — rotation frequency does
  not create per-operator identity, per-operator revocation, or attribution; those are the
  actual requirements, and only distinct accounts provide them.
- **Bootstrap the first ops via a CLI/seed script instead of a self-closing endpoint:**
  reasonable, but an endpoint keeps the surface uniform (one way to create ops), reuses the
  already-hardened denial-audit + rate-limit machinery, and needs no shell access to the
  running container. The self-close gives it the same fail-closed one-shot property a seed
  script would have.
- **Reopen the bootstrap gate when zero *active* ops remain (anti-lockout):** rejected —
  that turns the bootstrap token back into a standing backdoor. Instead the last-active-ops
  deactivation guard guarantees there is always at least one active operator, so the gate
  never needs to reopen; recovering from a hypothetical all-ops-disabled state is a
  deliberate DB-level action, not a token replay.
- **An `active` flag on an ops-only table rather than on `app_user`:** rejected — the flag
  is a general account property; putting it on `app_user` lets login enforce it for every
  role at no extra cost and keeps a single identity table.

## What a future SSO/OIDC integration replaces here

This surface is the seam for real operator SSO. When BioMech Health (or we) stand up an
IdP, an OIDC/SAML integration replaces **credential ownership and the first-ops
bootstrap**, not the authorization model: `require_ops` and the ops role stay; operators
would be provisioned/deprovisioned from the IdP (JIT on first federated login, or SCIM),
so `create_ops`/`deactivate_ops` become IdP-driven and `OPS_BOOTSTRAP_TOKEN` and
`/ops/accounts` retire entirely (the IdP is the new root of trust — no chicken-and-egg).
mTLS or IdP group claims could further scope operators (e.g. a provisioning-only vs.
read-only ops tier) by mapping claims to finer roles. The audit trail — already keyed on a
real operator id — carries straight over. Recording that here keeps the current design a
deliberate stepping stone, not a dead end.
