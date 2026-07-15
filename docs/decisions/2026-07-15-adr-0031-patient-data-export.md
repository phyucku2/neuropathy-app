# ADR-0031 — Patient data export ("Download my data", GET /me/export)

- **Status:** Accepted
- **Date:** 2026-07-15
- **Relates to:** ADR-0027 (account deletion — the sibling right-of-access feature;
  its patient-only + one-audit-event + storage-agnostic-service patterns are mirrored
  here), ADR-0010 (auth/user model, `require_patient`), ADR-0017 (the token vault whose
  contents must NEVER be exported), ADR-0006/0007 (research-grade observation record),
  ADR-0013/0020 (capability states), ADR-0012 (clinic connections), ADR-0024 (native
  platform seam), ADR-0022 (browser E2E DoD)

## Context

Deletion (ADR-0027) gave a patient the right to erase their record. Its counterpart —
the right of **access** — is a user-visible way to obtain a complete copy of that
record. It is good HIPAA hygiene (the individual right of access), a Play/store
expectation for apps that collect health data, and the natural safe companion to the
danger zone: *see everything we hold about you*, not just *destroy it*.

The record is spread across the same stores every feature reads: the account identity,
the Patient clinical row, the unified observation record (labs + BioMech + ADL), the
computed trajectory, the capability/consent states, and the clinic + EMR connection
metadata. Two of those stores hold **secrets that must never leave the system**: the
account's Argon2id password hash, and the EMR OAuth tokens in the encrypted vault
(referenced by `emr_connection.token_ref`). An export is a disclosure surface, so the
no-secrets rule is not a nicety — it is the load-bearing constraint.

## Decision

`GET /me/export` — patient role ONLY (`require_patient`; clinician/ops get 403, the
unauthenticated caller 401, exactly like `DELETE /auth/me`). It returns the patient's
COMPLETE record as one typed JSON envelope (`schemas/export.ExportOut`).

1. **Right-of-access framing, assembled from existing read paths.** A storage-agnostic
   `PatientDataExportService` (the deletion service's read-only twin) reads through the
   very repositories/services every other endpoint uses — `users.get_by_id` /
   `get_patient`, `observations.list_for_patient`, the shared trajectory engine
   (`compute_patient_trajectory`), `CapabilityService.effective_states`,
   `ClinicService.list_connections`, `emr_connections.list_for_patient`. No hand-rolled
   SQL, no second source of truth: the export reflects exactly what the app itself
   shows. Observations are the current analyzable set (the same predicate every read
   surface uses — errored/superseded rows are excluded there too).

2. **NO SECRETS, EVER — proven by ABSENCE.** The export is built from token-free
   *projections*, not model dumps:
   - the account profile carries `display_name/email/role/created_at` and has **no
     password-hash field**;
   - EMR connections reuse `schemas.emr.ConnectionOut`, which has **no `token_ref`
     field at all** — the vault reference is simply never carried, and the vault
     itself is never read;
   - clinic connections reuse `schemas.clinic.ConnectionOut` (names + status + dates,
     never tokens).
   The absence is *structural* (there is no field to leak into) and is proven the only
   honest way — by construction plus a test that serializes the payload and asserts the
   known token/`token_ref`/password-hash fixtures do **not** appear anywhere in it, over
   both storage modes (in-memory with the synthetic SMART tokens; Postgres with REAL
   vault ciphertext and the real Argon2id hash). Observation `payload`/`quality` DO
   travel — that is the patient's own health data, which is the whole point — but they
   never hold token material.

3. **Every export is audited — ONE PHI-free event.** A disclosure of the whole record
   is logged like any other PHI read (CLAUDE.md §5): one `export_account` audit event,
   actor = the patient, detail = **counts only** (observations / emr_connections /
   clinic_connections / capabilities) — never values, names, or emails.

4. **Envelope for forward-compat.** The payload wraps the data in
   `{exported_at, schema_version, subject_id}`. `schema_version` ("1.0") lets later
   tooling interpret an older downloaded file; it is bumped on any breaking shape change.

5. **Native share vs. web download (ADR-0024 seam).** The delivery is platform-selected
   behind one injectable seam (`src/native/exportData.ts`), `isNativePlatform()`-gated
   so the web build/E2E never touch a plugin:
   - **Web** triggers a Blob + object-URL file download of the JSON
     (`neuropathy-export-YYYY-MM-DD.json`) AND a flattened CSV of the observations
     table (a small pure, unit-locked helper — a spreadsheet-friendly scalar view; the
     nested detail stays in the JSON).
   - **Native** writes the JSON to the app cache directory (`@capacitor/filesystem`,
     Cap-6 line) and opens the OS Share sheet (`@capacitor/share`, Cap-6 line) — a phone
     has no browser "download", so sharing a written file is the platform equivalent.
   Both plugins are MIT and register warning-free under `cap sync` (Cap-6, verified the
   ADR-0024 way); the gradle registration is committed.

6. **Dual-store parity.** The service is wired in `deps.py` for both modes: per-request
   Postgres repositories (clinic/capability services composed on the SAME session so
   their reads join the transaction), or the shared in-memory singletons every feature
   uses. A minimal read-only extension — `UserRecord.created_at` and a
   `UserRepository.get_patient` returning a non-secret `PatientRecord` — surfaces the
   account/patient timestamps and connection mode through the store that already OWNS
   the Patient row (the same store `delete_with_patient` destroys it through); no new
   table or migration.

### Frontend

Settings gains a **"Download my data" card** placed ABOVE the danger zone and clearly
separated from it — the safe, reassuring counterpart to deletion. One button fetches
the export and hands it to the delivery seam; while in flight a `role=status`
("Preparing your data…") shows and the button is disabled; success shows a brief
`role=status`; any API failure is surfaced verbatim in a `role=alert`.

## Verification boundary

Backend unit + live-Postgres integration cover: the happy path exporting every data
class with correct values and provenance; the no-secrets guarantee proven by scanning
the serialized payload for the real token/`token_ref`/hash fixtures (absent);
clinician 403, ops 403, unauthenticated 401; the one PHI-free `export_account` audit
event (counts only); an empty account exporting honest empty collections; the route's
ExportError mapping; 100% coverage on the new code; ruff + ruff format + mypy --strict
clean. Frontend unit locks the CSV flattener (escaping, header-only-when-empty), the
web download seam (blob path) and the native seam (write-file + Share via injected
fakes), and the card (pending/success/verbatim-error, seam delegation, position above
the danger zone). The browser E2E drives the BUILT bundle: the card renders and a real
Blob download fires in Chromium, with the mock recording exactly one export and zero
console errors.

NOT verified here: on-device Share-sheet UX (no Android SDK locally — same boundary as
ADR-0023/0024; `npx cap run android` is the on-device proof). The export reflects the
current analyzable record (superseded/errored observation rows are excluded, exactly as
on every other read surface) — a full immutable audit-trail export was not in scope.

## Options considered

- **Dump the ORM models / include everything:** rejected — a model dump would carry
  `password_hash` and `token_ref`; typed token-free projections make the leak
  structurally impossible and reviewable in one place.
- **Read the vault and include decrypted EMR tokens "for completeness":** rejected
  outright — exporting live OAuth bearer tokens would hand every reader of the file a
  key to the patient's EHR. Connection *metadata* is the record; the tokens are not.
- **A single JSON only (no CSV):** rejected for web — a flat observations CSV is what a
  patient can actually open in a spreadsheet; the JSON remains the complete form.
- **A new top-level export table / async job:** deferred — the record is small and
  assembled synchronously from existing reads; a background job (large exports, signed
  URLs) can wrap this endpoint later without changing its contract.
- **No `schema_version`:** rejected — a downloaded file outlives the app version that
  produced it; the version stamp is cheap forward-compat.
