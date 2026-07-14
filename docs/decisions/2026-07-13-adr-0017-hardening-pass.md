# ADR-0017: Hardening Pass — Rate Limiting, Durable OAuth State, Encrypted Token Vault, Ops-Gate Hardening, Blocking Scans

**Date:** 2026-07-13
**Status:** Accepted
**Builds on:** ADR-0008/0009 (SMART flow whose state becomes durable here), ADR-0012
(clinician surface; the invitation rate-limit deferral and the bootstrap gate), and
the Postgres-durability posture (request-scoped transactions, files-only migrations).

## Context

Four documented deferrals were open (deps.py, ADR-0012, roadmap): invitations had no
rate limit (the non-enumeration posture bounded what a probe reveals, not how often
one may probe); the OAuth state->PKCE-verifier map and the OAuth token vault were
per-process in-memory singletons (a restart or a second worker broke callbacks and
pulls); the ops bootstrap token accepted any length and failed silently; and CI's
Python vulnerability/license steps were non-blocking placeholders.

## Decision

### 1. Invitation rate limiting — sliding window counted from the audit log

`SlidingWindowRateLimiter` (app/services/rate_limit.py) is pure, dependency-free
window math over a `RateLimitCounter` protocol; time is always injected (`now=`),
never read from the wall clock, so tests lock the window arithmetic on fixed
timestamps (the ADR-0013 CI-flake rule). **The counter is the audit log itself**:
`AuditEventRepository.count_actor_events_since` counts one actor's
`invite_patient` events inside the trailing window (settings-driven: default 20 per
3600 s). Chosen over a new `rate_limit_event` table because the invite flow already
writes exactly one audit event per accepted attempt into a durable, append-only
store — a second table would be a dual-write that can drift from the audited truth,
and the audit trail is already the thing we trust for accountability. Cost: one
indexed count per invite (`ix_audit_event_actor_action_time`, migration 0004),
within the write budget.

Postures:

- **The limiter fires BEFORE the email lookup.** A 429 is decided from the actor's
  own history alone, so it cannot depend on — or reveal — whether the probed email
  matches an account; the ADR-0012 non-enumeration property is preserved under
  refusal, and an enumeration campaign is slowed to the window budget.
- Refusals answer **429 with a friendly retriable message** and are audited
  (`action='rate_limited'`, counts/config only, never the email — which was never
  looked up). Refusals do NOT count toward the limit, so a refused clinician's
  budget frees as the window slides instead of extending their own lockout.
- Denials (this 429 and the bootstrap 403 below) are **returned responses, never
  raised HTTPExceptions**: a raised exception propagates through the
  request-transaction dependency and would roll the refusal's audit event back in
  DB mode; the integration suite pins the committed-audit behavior.
- No `Retry-After` header: a count-only counter cannot cheaply know when the oldest
  event leaves the window; the message says "try again in a little while."
- Postgres-mode concurrency: audit events commit with their request transaction, so
  N in-flight parallel requests can each admit before seeing each other — a bounded,
  transient overage (at most the in-flight concurrency), acceptable for an abuse
  brake that is not a billing meter.

### 2. DB-backed pending-auth store (single-use, TTL)

New `pending_auth` table (migration 0004): `state` PK, `connection_id` FK,
`code_verifier`, `token_endpoint`, `created_at`, `expires_at` (indexed). The columns
are exactly what `complete_callback` needs to finish the exchange — `patient_id` and
`fhir_base` already live on the referenced `emr_connection` row and are not
duplicated. `PendingAuthStore` is now a Protocol (put/consume) with:

- `InMemoryPendingAuthStore` — the previous dict behavior wrapped, now TTL-aware;
  still the process singleton for in-memory mode.
- `PostgresPendingAuthStore` — constructed per request in DB mode. **Single-use is
  enforced by the database**: `consume` is one `DELETE ... RETURNING`, so of two
  callbacks racing on the same state the second waits on the row lock and then
  deletes nothing — exactly one wins, no check-then-delete window.

Entries expire `settings.pending_auth_ttl_seconds` (default 600) after `put`;
expired states are rejected (same 404 as unknown/replayed states) and purged
opportunistically (every `put` sweeps, and a consumed-but-expired row is already
deleted). In DB mode a FAILED token exchange rolls the consumption back with the
rest of the request transaction, so the patient may retry the callback; single-use
holds for every committed outcome. The code verifier is stored in the clear, deliberately: it is not a bearer
credential (useless without the intercepted authorization code and our client
identity), lives for minutes, and is single-use — encrypting it would gate login on
the secret-store key without a matching threat.

### 3. Encrypted-at-rest token vault

New `secret` table (migration 0004): `ref` PK, `ciphertext` (BYTEA), `created_at`.
`SecretStore` is now an async Protocol; `PostgresSecretStore` encrypts token
material with **Fernet** (AES-128-CBC + HMAC-SHA256, from `cryptography` — now a
direct dependency, Apache-2.0 OR BSD-3-Clause; it was already in the tree via
`pyjwt[crypto]`) keyed by `settings.secret_store_key`, a base64 Fernet key that
lives only in the environment (`.env.example` documents generation; validated at
settings load — a malformed key stops boot).

**Fail closed, never fail plaintext:** in DB mode WITHOUT a configured key, the app
keeps the per-process in-memory vault (logged once at first use; tokens then do not
survive restarts). Plaintext secret material never reaches the database under any
configuration. A rotated/wrong key makes old ciphertext undecryptable; `get` returns
None and the pull path answers the existing 409 "reconnect your EMR" — key rotation
with re-encryption is out of scope (patients re-link).

**Deletion on revoke and re-link (adversarial-review finding):** a durable vault
must not out-retain the grant it protects — the old process-memory vault forgot
revoked tokens on restart, and the DB vault must be no weaker: a patient who revoked
must not stay one database dump + key away from a working refresh token months
later. `SecretStore` therefore carries `delete(ref)` (in-memory pop; Postgres row
DELETE), `EmrService.revoke` deletes the vaulted tokens and clears `token_ref` when
it flips the status, and a re-link (`complete_callback` on a connection that already
holds a `token_ref`) deletes the superseded secret before vaulting the new one — no
orphaned ciphertext either way. Rows orphaned by the earlier flows do not exist
pre-launch, so there is nothing to backfill.

### 4. Ops bootstrap gate hardening

The bootstrap token keeps its constant-time compare and fail-closed-when-unset 403,
and gains: (a) **minimum length enforced at settings load** — a configured
`OPS_BOOTSTRAP_TOKEN` under 32 chars stops boot with a generation hint (fail closed:
a short token is a guessable ops gate), and the load-time error **never echoes the
rejected value** (`hide_input_in_errors`; adversarial-review finding — pydantic's
default rendering appends `input_value=...`, which would print a nearly-valid token
or secret-store key verbatim into boot-loop logs); (b) **failed attempts are
audited** (`action='bootstrap_denied'`, actor_role='ops', actor_id = a fixed
sentinel uuid5 for 'ops-bootstrap', detail = failure shape only — never token
material), so brute-forcing leaves a trail. Denial audits are **capped by the same
sliding-window limiter** counting the `bootstrap_denied` events themselves under
that sentinel (settings-driven: default 20 per 3600 s; adversarial-review finding):
the endpoint is unauthenticated, so unbounded per-request audit writes were a
log-flood/DoS primitive against the PHI database. Beyond the cap the byte-identical
403 still answers and only the audit write is skipped. **Tradeoff, accepted:** the
forensic trail of a sustained brute-force is bounded to the window budget (the
first N attempts per window are recorded; the tail is not) in exchange for a
bounded audit table — an attacker can no longer grow it without limit, and a
capped-out window is itself the loudest possible signal in the recorded rows.
(c) This gate remains interim: **a dedicated ops-auth surface (SSO/mTLS-backed)
replaces the bootstrap token at production readiness** — that surface is out of
scope for this pass and stays on the roadmap as the ADR-0010/0012 follow-up.

### 5. CI: Python security/license scans now block

The security job installs the backend into an isolated venv (pip-audit cannot parse
our pyproject directly; the installed environment is the real resolved tree) and
runs, blocking: `pip-licenses --python <scan-env> --allow-only <permissive list>`
(CLAUDE.md §4, spelled as the tree spells them: MIT/BSD/Apache variants, ISC,
PSF-2.0, MIT-0, Unlicense) and then pip-audit. Both scan tools live OUTSIDE the
scan venv and judge it from there (adversarial-review finding: pip-audit was
installed INTO the scan env, so its own ~26 dependencies — requests, urllib3,
rich, ... — joined the audited set and could gate merges, contradicting the venv's
whole purpose). pip-audit audits a fully pinned freeze snapshot:
`<scan-env>/bin/pip freeze --exclude-editable` (drops only our own unpublished
package) piped to `pip-audit -r <snapshot> --no-deps` (the snapshot IS the resolved
tree; nothing left to resolve) — every real dependency is audited and any known
vulnerability fails CI.
**Documented exception:** `certifi` (MPL-2.0) is skipped by name in the license
gate — it is the Mozilla CA certificate bundle consumed unmodified as data via
httpx, and MPL's file-level terms are met by upstream; no other MPL dependency is
admitted (anything new fails the allowlist and lands here for review).

## Consequences

- Migration 0004: `pending_auth` + `secret` tables and
  `ix_audit_event_actor_action_time`; models added so autogenerate parity holds.
  Downgrade drops both tables — they hold only transient, re-obtainable OAuth state
  (handshakes in flight; tokens the patient re-grants by reconnecting), never
  health data, so unlike 0002 there is nothing to refuse over.
- Config: `secret_store_key`, `pending_auth_ttl_seconds`, `invite_rate_limit_max`,
  `invite_rate_limit_window_seconds`, `bootstrap_denied_audit_max`,
  `bootstrap_denied_audit_window_seconds`; startup validation on
  `ops_bootstrap_token` and `secret_store_key` (rejected values are never echoed
  into the error). `.env.example` (placeholders only) is now committed;
  `.gitignore` un-ignores exactly that file.
- deps.py: DB mode wires `PostgresPendingAuthStore` per request and
  `PostgresSecretStore` when the key is configured; in-memory mode is unchanged.
  `SecretStore.put/get` became async (the Postgres implementation awaits I/O).
- A multi-worker DB deployment now completes connect->callback across workers and
  keeps pulled-token access across restarts (with the key configured) — the two
  README "known limitations" are retired.
- Tests: limiter window math on fixed timestamps; 429 + refusal audit +
  limiter-before-lookup order; pending-auth TTL/single-use incl. a live two-session
  consume race; Fernet round-trip + ciphertext-not-plaintext + wrong-key fail-closed;
  bootstrap min-length rejection (asserting the rejected value never appears in the
  error) + denied-attempt audit + denial-audit cap (identical 403 beyond it, audits
  resume once the window passes — fixed timestamps); token deletion on revoke and
  re-link (in-memory and Postgres: secret row gone, pull after revoke still 409s);
  migration 0004 upgrade/downgrade/re-upgrade with autogenerate parity.

## Options considered

- **A `rate_limit_event` table:** rejected — a dual-write beside an append-only log
  that already records exactly the counted events; drift between them would make the
  limiter lie about the audited truth.
- **Fixed-window counters (cheaper):** rejected — window-edge bursts allow 2x the
  budget; the sliding count is one indexed query and invitations are low-volume.
- **Counting `rate_limited` refusals toward the limit:** rejected — refusals would
  extend the actor's own lockout indefinitely under retries; the brake should
  release as the window slides.
- **Encrypting the PKCE verifier in `pending_auth`:** rejected — minutes-lived,
  single-use, not a bearer credential; would couple the login flow to the
  secret-store key without a matching threat.
- **Plaintext token rows when no key is configured:** rejected outright — the vault
  fails closed to the in-memory store; secrets never reach the database unencrypted.
- **External secret manager (AWS/GCP/Vault) now:** deferred — the SecretStore
  protocol is the seam; the encrypted DB vault meets encryption-at-rest with zero
  new infrastructure, and a managed-KMS adapter can replace the implementation
  without touching the flow.
- **Allowing MPL-2.0 generally in the license gate:** rejected — only `certifi` is
  vetted; a blanket allow would admit future MPL code silently.
