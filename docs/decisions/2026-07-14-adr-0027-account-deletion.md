# ADR-0027 — Patient account & data deletion (DELETE /auth/me)

- **Status:** Accepted
- **Date:** 2026-07-14
- **Relates to:** ADR-0026 (recorded the gap: hard Google Play requirement), ADR-0017
  (token-vault deletion-on-revoke seam, reused), ADR-0013 ("revocation is never
  blockable", mirrored), ADR-0010 (Argon2id verify, reused), ADR-0019 (refresh
  re-reads the user — deletion kills the refresh token for free)

## Context

Google Play requires a user-visible account & data deletion path for apps that collect
user data (ADR-0026 recorded it as the required pre-store portion), and deleting a
patient's record on request is good HIPAA hygiene regardless of store policy. The API
had revocation and deletion *seams* (vault `delete`, per-account deactivation) but no
flow a patient could invoke to destroy their account and every datum it owns. Two
tensions had to be settled: the audit log is retained for regulatory reasons but holds
an FK to the patient row it must outlive, and the observation store is append-only by
research-grade design (ADR-0006) yet must be erasable on the owner's request.

## Decision

`DELETE /auth/me` — patient role ONLY (`require_patient`; clinician/ops get 403 —
their accounts are provisioned and are deprovisioned by ops, not self-deleted).

1. **Fresh password re-authentication.** The request body carries the account
   password, verified with the same Argon2id primitive login uses. A bearer token
   proves possession of a session; only the password proves the account owner is
   asking — a stolen token alone must never be able to destroy an account. A mismatch
   answers 403 with a friendly, verbatim-shown detail ("That password didn't match.
   Nothing was deleted.") — the caller is already authenticated, so this reveals
   nothing about other accounts. Nothing is written before the verify, so the refusal
   raise is safe under the request-transaction rule (docs/lessons.md "return don't
   raise" applies only when an audit row must survive the denial; deletion refusals
   are deliberately not audited — an unbounded per-request audit write on a
   password-guessing surface would be the ADR-0017 log-flood primitive again).
2. **Transactional and never blockable.** The whole deletion runs in the one
   request-scoped transaction (commit or nothing). The route carries NO
   `require_capability` gate: like revocation (ADR-0013), the way OUT is never
   gated by a toggle or ops kill switch — proven by a test that ops-kills every
   registry capability and deletes anyway.
3. **One PHI-free audit event, written BEFORE the destructive statements, in the
   same transaction.** `action='delete_account'`, actor = the patient user, detail =
   row counts only (emr_connections / vault_secrets / clinic_connections /
   patient_capabilities) — references and counts, never values, per the audit
   contract.
4. **FK-safe destruction order, patient row last:** pending_auth rows for the
   patient's EMR connections → the vaulted OAuth secrets for those connections —
   through the SAME `SecretStore.delete` seam ADR-0017 revocation uses, never a
   second crypto path → emr_connection rows → clinic_connection rows (ending any
   live consent) → patient_capability rows → observation rows (the self-referencing
   supersede FK is cleared first — `revises_id` NULLed for the patient, then one
   DELETE takes the whole chain; supersession never crosses patients) → the app_user
   row → the patient row LAST.
5. **Audit retention: `audit_event.patient_id` becomes ON DELETE SET NULL**
   (files-only migration 0006, model updated for autogenerate parity). Audit events
   are PHI-free by contract, so they are RETAINED under regulatory retention and the
   patient-row delete detaches them — the history, including the deletion event
   itself, survives as anonymous events instead of blocking the delete or being
   cascaded away. Downgrade restores the plain FK (always safe: the column is
   nullable and remaining values reference live patients). The in-memory audit store
   mirrors the detach via `detach_patient` (the Postgres twin is a documented
   defense-in-depth no-op — the FK has already fired).
6. **Erasure beats append-only, on request.** ALCOA/append-only (ADR-0006) governs
   corrections — values are never *overwritten*. The subject's right to erase their
   record is a different operation: every observation row (all statuses, superseded
   rows included) is destroyed.
7. **Storage-mode parity.** `AccountDeletionService` is storage-agnostic over the
   repository Protocols; deps.py wires Postgres twins per request and one in-memory
   singleton composed of the SAME stores every other feature singleton uses — so
   the no-DATABASE_URL mode deletes exactly the data those features wrote.
8. **Token death needs no new machinery.** `get_current_user` re-reads the user
   (401 "Account no longer exists") and `/auth/refresh` re-reads it too (ADR-0019),
   so the live access token, the refresh token, and any second delete attempt all
   die with the row — pinned by tests, not assumed.

### Frontend

Settings gains a clearly-separated **Danger zone** card at the bottom: "Delete my
account" expands to (a) the password field, (b) a checkbox acknowledging permanent
deletion of all health data, then (c) the same two-tap confirm pattern as
ConnectionRow's disconnect. While pending, every control is disabled; a wrong
password shows the API detail verbatim in a `role=alert`. On success the client
clears the session and lands on `/login` with a transient "Your account and data
were deleted." notice carried in router state — no new route, and any navigation or
reload naturally clears it.

## Verification boundary

Unit + live-Postgres integration suites cover: every table's rows destroyed
(counted 0 across app_user, patient, emr_connection, pending_auth,
clinic_connection, patient_capability, observation; vault ciphertext row gone);
wrong password → 403 + nothing deleted + no audit event; clinician/ops → 403;
post-deletion login/refresh/me/second-delete → 401; audit rows retained with
patient_id NULL (FK behavior also proven in isolation); another patient's data and
non-anonymized audit trail untouched; migration 0006 down/up with autogenerate
parity. The browser E2E drives the built bundle through the danger zone to the
login screen with zero console errors and asserts the mock API recorded exactly one
deletion. NOT verified here: the Play Data Safety form linkage (submission-time,
user-side) and any server-side EMR-token *revocation at the EHR* (we delete our
copies; upstream grant revocation at the vendor is the patient's portal action —
same posture as ADR-0017 revoke).

## Options considered

- **Soft-delete / deactivate-only (flip `active` off):** rejected as the deletion
  mechanism — Play requires data deletion, HIPAA hygiene wants the PHI gone, and a
  "deleted" account whose observations persist is a false promise. Deactivation
  (ADR-0019) remains the ops tool; deletion is the patient's.
- **Cascade FKs (`ON DELETE CASCADE`) instead of explicit ordered deletes:**
  rejected — a schema-wide cascade silently deletes whatever future tables point at
  patient, and would have cascaded the audit log away; explicit order keeps every
  destruction visible in one reviewed code path and lets audit_event alone SET NULL.
- **Auditing the retained history's anonymization as separate events:** rejected —
  the SET NULL is the retention design itself; one `delete_account` event records
  the erasure.
- **Grace period / delayed deletion job:** deferred — Play accepts immediate
  deletion; a cooling-off window is a product decision (owner call) and can wrap
  this endpoint later without changing it.
- **Deleting the audit rows too ("full wipe"):** rejected — the events are PHI-free
  by construction and are the regulatory/forensic record that the erasure happened;
  retaining them anonymous serves both HIPAA accountability and the patient.
