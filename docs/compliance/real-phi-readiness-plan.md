# Real‑PHI Readiness — HIPAA Hardening Plan

**Date:** 2026‑07‑20 · **Trigger:** ADR‑0048 introduces name + DOB + Medicare Beneficiary
Identifier (MBI) — an unambiguous HIPAA identifier — so the platform must move from
"synthetic‑only, pre‑BAA" toward genuine real‑PHI readiness.

This is a **readiness plan, not a compliance attestation.** Today's synthetic‑only, pre‑BAA posture
is correct and nothing here is certified. Source: the 2026‑07‑20 HIPAA Security‑Rule assessment
(10 dimensions, 61 gaps: 10 critical / 24 high / 20 medium / 7 low; 30 go‑live gates; ~31 code /
30 process).

## What is already strong (do not re‑litigate)

- **Access‑control core** — unique UUID per principal, three roles gated centrally, `user.active`
  re‑checked every request, the single `_may_read_patient` consent predicate feeding
  panel/views/writes, neutral 404‑over‑403, per‑operator ops accounts.
- **Auth primitives** — Argon2id, kind‑enforced HS256 JWTs, non‑enumerating login, fresh re‑auth
  for deletion, multi‑worker JWT‑secret hard‑fail.
- **PHI‑free telemetry seam** — route‑template logging, subject‑free metrics, error reporter shipping
  only the exception type (for app‑authored logs).
- **Integrity design** — append‑only Observation, corrections‑as‑new‑rows via `revises_id`,
  provenance in `quality`.
- **Lifecycle** — transactional right‑to‑erasure (ADR‑0027), §164.524 export (ADR‑0031), backup drill
  with the SECRET_STORE_KEY‑pairing warning.
- **Secret‑vault design** — Fernet vault holds only ciphertext; key outside repo/DB; fails closed to
  per‑process memory, never plaintext.

The dominant deficits are **organizational controls that don't yet exist** and **the entirely‑unbuilt
MBI surface** — not the shipped clinical‑data code.

## 1. Hard go‑live gates — must close before ANY real PHI/MBI

### 1A · Process / owner (no code substitute — the critical path)

| # | Gate | HIPAA |
|---|------|-------|
| P1 | Documented enterprise **Risk Analysis** of production (must enumerate ADR‑0048 assets) | §164.308(a)(1)(ii)(A) |
| P2 | **Named Security Official** (+ Privacy Official) in writing | §164.308(a)(2); §164.530 |
| P3 | **Microsoft Azure BAA/DPA confirmed** for the exact subscription + Container Apps + Postgres + Monitor | §164.308(b)(1)/§164.314(a) |
| P4 | **BioMech role determination + BAA**, added to the BAA inventory (currently absent) | §164.308(b)(1)/§164.314(a) |
| P5 | **Workforce training** (now incl. clinic dashboard staff + BioMech intake; MBI minimum‑necessary) | §164.308(a)(5) |
| P6 | **Incident‑response operating program** (roles, register, breach‑determination owner, one tabletop) | §164.308(a)(6)(ii) |
| P7 | **Contingency**: RPO/RTO, DR plan, emergency‑mode, criticality analysis + a DR test | §164.308(a)(7) |
| P8 | **Verify + document bulk ePHI‑at‑rest encryption** (Azure SSE + backup encryption; consider CMK/Key Vault for MBI) | §164.312(a)(2)(iv) |
| P9 | **Retention/disposal schedule** (health data, audit ≥6 yr, backups) + bounded backup expiry; reconcile the deletion promise vs backup residual | §164.316(b)(2); §164.310(d)(2)(i) |
| P10 | **SECRET_STORE_KEY backup + rotation operationalized** (secret manager, paired snapshot, MultiFernet, paired‑key DR restore) | §164.308(a)(7) |
| P11 | **`allowInsecure:true` internal hop risk‑accepted in writing** (with confirmed network isolation) or replaced | §164.312(e)(1) |
| P12 | **§164.526 right‑to‑amend process** stood up (technical intake reuses the correction backlog item) | §164.526 |

> Emergency‑access / break‑glass (§164.312(a)(2)(ii), a *required* spec) has no procedure — the
> Security Official should author it in the same policy pass.

### 1B · Code go‑live gates (build before flipping to real PHI)

| # | Gate | Approach |
|---|------|----------|
| C1 | **Fail‑closed `SECRET_STORE_KEY` in prod** | `main.py` serving guard hard‑fails when key unset + `DATABASE_URL` set (today only warns) — closes incomplete erasure + unencrypted EMR tokens |
| C2 | **Enforce Postgres TLS structurally** | `create_async_engine` with an `ssl.SSLContext`; move `ssl=require` → `verify-full` with Azure CA; fail closed if the prod URL lacks SSL |
| C3 | **Contain server tracebacks + kill input echo** | catch‑all exception handler → generic 500 + PHI‑free event; `hide_input_in_errors=True`; wrap FHIR/biomech/identity construction so ValidationErrors don't log `input_value=<PHI>` |
| C4 | **Fail‑closed `APP_DEBUG`** | hard‑fail boot if debug true while prod (debug returns per‑frame locals = raw PHI) |
| C5 | **Rate‑limit `/auth/login` + `/auth/refresh`** | existing `SlidingWindowRateLimiter`, keyed IP + email‑hash, 429 before Argon2 verify, anti‑enumeration preserved (login is currently unthrottled) |
| C6 | **MFA for clinician + ops** | TOTP (pyotp secret in the vault) or WebAuthn; step‑up gate; forced first‑login enrollment |

## 2. Code‑hardening backlog (after current in‑flight work; ranked)

1. **DB‑level append‑only (WORM)** — least‑privilege app role (no UPDATE/DELETE) + reject trigger; erasure via a separate privileged role. *(also closes improper‑destruction)*
2. **Correction / `entered_in_error` service** — capability‑gated superseding row + required reason + distinct audit; also the technical intake for §164.526 (P12).
3. **Drop mutable `updated_at`/`onupdate` from Observation** — created‑only mixin.
4. **Cryptographic tamper‑evidence** — keyed HMAC per Observation row and/or hash‑chained audit log.
5. **Automatic logoff / inactivity timeout** — refresh rotation with idle‑expiry + client idle‑logoff.
6. **Vault key → Azure Key Vault reference** (CMK/HSM for MBI‑grade).
7. **HSTS + HTTP→HTTPS enforcement**.
8. **Breached‑password screening** (HIBP k‑anonymity); longer min for privileged roles.
9. **Keep nginx error_log / OAuth code+state out of the query string** (sweep #2 tail).
10. **Replace `detail=str(exc)` echoes** (ingestion/biomech) with static messages.
11. **Pin Argon2id cost parameters**.
12. **Per‑token (JTI) revocation** or formally accept TTL+deactivation.
13. **AI‑narration post‑deletion cleanup** (only if narration becomes durable).

## 3. Owner / process actions (beyond the go‑live gates)

Owned by the Security Official (P2), not blocked by code: risk‑management plan; formal HIPAA
policy set (security/privacy/sanction/access/retention + emergency‑access + minimum‑necessary);
access‑authorization policy + role/permission matrix; workforce clearance/termination procedures;
scheduled activity‑review (named reviewer + cadence); sanction policy; periodic evaluation
(annual + change‑driven); CI lint enforcing PHI‑free telemetry; counsel confirmation of the
§164.524 designated‑record‑set scope and the NPP.

## 4. MBI‑specific controls — ADR‑0048 must adopt BEFORE its build

**Spec amendments (applied to ADR‑0048 §"Security hardening amendments"):**

1. **Match token = keyed HMAC, not a plain salted hash** — an 11‑char fixed‑format MBI with a
   deterministic (non‑per‑row) salt is brute‑forceable, so a plain hash is **still PHI**. Use
   HMAC‑SHA256 (or Argon2id + fixed pepper) with the **pepper in the vault/KMS, never in DB/code**;
   state the token is PHI. §164.514(b)(2); §164.312(a)(2)(iv).
2. **No clinical data binds before confirmation; wrong‑match flow is required, not deferred** — as
   originally written, BioMech data auto‑attaches to a shell on the clinician's order *before* patient
   confirmation, so a mis‑keyed MBI silently binds one patient's PHI to another. Gate attach on the
   patient claim (or explicit clinic verification); publish the name‑normalization algorithm; treat a
   non‑unique/conflicting triple as manual review; make wrong‑match correction/merge an audited,
   reversible flow. §164.312(a)(1); §164.502(a); §164.312(c)(1).
3. **At‑visit consent modeled as a §164.508 authorization** — add an append‑only, versioned
   `EnrollmentAuthorization` (attesting principal, timestamp, instrument+version, scope); pre‑activation
   revocation → shell purge + BioMech detach; accountable under §164.528. §164.508; §164.528.
4. **Claim bound to the enrollment token, not a standalone name+DOB+MBI lookup** — otherwise the claim
   is an enumeration + MBI‑validation oracle. Require token possession; verify the triple only within
   token scope; per‑token + per‑IP caps, equalized responses, lockout + audit. §164.312(a)(1); §164.514.
5. **Least‑privilege, separately‑audited identity/MBI read path** — a distinct capability key + a
   distinct `read_identity` audit action (refs/counts only, never the MBI); dashboard shows status only.
6. **`SECRET_STORE_KEY` co‑required with the MBI feature; MultiFernet rotation** — config validator
   *enforces* the key when the enrollment flag is on (fail closed, never plaintext).
7. **Enrollment identity in erasure + export** — add the identity store to the FK‑safe deletion order;
   purge the encrypted MBI via `SecretStore.delete`; include in `/me/export`; test zero residual.
8. **Audit/log/display discipline enforced, not asserted** — regression tests forbidding raw
   identifiers in audit detail/errors; **remove the "last‑4" MBI display** (last‑4 beside name+DOB is
   still an identifier).
9. **Hash‑only default until D1** — no raw MBI at rest until the reimbursement path is unblocked
   (behind a feature flag). §164.514(d); §164.502(b).
10. **Retention/purge for unclaimed shells** — stalled‑shell window with automated MBI purge; an
    audited ops/clinic administrative correct‑and‑delete for non‑app subjects.
11. **BioMech BAA + role classification** (= P4) before any real MBI moves.

---

*Prepared by an internal engineering assessment as a readiness plan; not legal advice and not a
claim of HIPAA compliance. Organizational determinations rest with the Security Official and counsel.
Pairs with `docs/compliance/gap-register/` and `docs/compliance/baa-inventory.md`.*
