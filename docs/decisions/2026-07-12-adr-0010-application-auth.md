# ADR-0010: Application Authentication & Session Model

**Date:** 2026-07-12
**Status:** Accepted
**Closes:** the "patient_id passed explicitly" placeholder from ADR-0009.

## Context

Every patient-scoped endpoint needs a real identity: who is calling, which patient
record they own, and (later) which clinic role they hold. Biometric login (Face ID /
fingerprint, per requirements v1) is a **device-side unlock** — the server still needs
a standard token-based session model underneath it.

## Decision

- **Passwords:** hashed with **Argon2id** (`argon2-cffi`, MIT) — the current OWASP
  first-choice password hash. Minimum length 8 (NIST 800-63B); no composition rules.
- **Sessions:** JWT **access tokens (15 min)** + **refresh tokens (30 days)**, HS256
  with a server-side secret. Claims: `sub` (user id), `role`, `kind`
  (access|refresh), `iat`, `exp`, `jti`. A refresh token cannot be used as an access
  token (kind is enforced), and vice versa.
- **Biometrics fit:** the mobile app stores the refresh token in the platform keystore
  (Keychain/Keystore) gated behind Face ID / fingerprint. Biometric unlock releases
  the stored token; the server only ever sees standard bearer tokens.
- **Identity vs. clinical record:** `User` (auth identity: email, hash, role) is
  separate from `Patient` (clinical record); a patient user carries a `patient_id`
  link. Roles: `patient`, `clinician`, `ops`. Registration creates patient users;
  clinician/ops accounts are provisioned, not self-registered.
- **Ownership enforcement:** patient-scoped resources (e.g. EMR connections) are
  readable/actionable **only by the owning user** — enforced server-side, verified by
  tests (cross-user access → 403).
- **Endpoints:** `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`,
  `GET /auth/me`. Auth errors are 401 with `WWW-Authenticate: Bearer`.
- **Secret handling:** `JWT_SECRET` from the environment/secret manager. If unset
  (dev), an ephemeral random secret is generated at startup — sessions simply don't
  survive restarts; there is no hard-coded fallback secret.

## Storage posture

Same as ADR-0009: user records live in an in-memory repository behind the interface
the Postgres implementation will use. Token *verification* is stateless (JWT), so the
swap doesn't touch session logic. Refresh-token revocation lists arrive with the DB.

## Follow-ups (explicit)

- DB-backed user store + refresh-token revocation/rotation.
- Rate limiting + lockout on login; email verification; password reset flow.
- Clinician SSO options for the clinic version (their EMR identity — ADR-0009's
  EHR-launch path already carries the clinician context).

## Options considered

- **Managed auth (Auth0/Cognito/Firebase):** viable, but adds a PHI-adjacent vendor
  (BAA needed), per-MAU cost, and lock-in; our needs are standard and small. Revisit
  if SSO/enterprise requirements balloon.
- **Sessions in server-side store (opaque cookies):** better revocation, but poor fit
  for mobile API clients vs. bearer tokens; JWT + short access TTL chosen.
- **Argon2id + JWT (chosen).**
