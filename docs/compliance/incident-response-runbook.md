# Incident response runbook

A practical runbook for a suspected security incident or PHI breach in the neuropathy app.
Recorded under **ADR-0021**. Aligns to the HIPAA Security Rule incident procedures
(§164.308(a)(6)) and Breach Notification Rule (§164.400–414).

> **Not legal advice.** The **covered entity** (BioMech Health as operator) owns breach
> declaration, the risk assessment, and all notifications; several steps here require its
> counsel and its own policies. This runbook gives responders the app-specific detection,
> containment, and evidence steps, and flags every decision that is **[CE]** (covered-entity
> / legal).

## Roles (fill in — [CE])

| Role | Who |
|---|---|
| Incident Commander | ☐ [CE] |
| Privacy/Security Officer (breach determination) | ☐ [CE] |
| Engineering on-call | ☐ [CE] |
| Legal / compliance | ☐ [CE] |
| Communications | ☐ [CE] |

## 1. Detect

Sources that surface an incident (all PHI-free — ADR-0018/0021):

- **Alerts** (`docs/ops/observability.md`): `HighServerErrorRate`, `ElevatedAuthDenials`
  (401/403 spike — possible credential stuffing), `ElevatedRateLimiting` (429),
  `ReadinessFlapping`, `DbPoolNearExhaustion`, `BackendDown`.
- **Audit log** (immutable, append-only): unexpected PHI **reads/writes**, provisioning, or
  consent changes — actor id/role + action + patient reference + counts, never values.
- **Error events** (if the error seam is enabled): a spike of a given `exception_type` on a
  route template, correlated to request logs via `request_id`.
- **External report** (patient, clinician, provider, researcher).

Record: first-observed time (UTC), who/what detected it, the signal, and a running timeline.

## 2. Contain

Act to stop ongoing exposure without destroying evidence:

- **Revoke access**: deactivate the implicated operator/clinician/patient account
  (per-operator deactivation, ADR-0019) — a deactivated principal of any role is refused at
  authentication within the access-token TTL. Rotate `JWT_SECRET` to invalidate **all**
  live sessions if token compromise is suspected (forces re-login; ADR-0010).
- **Cut a leaking integration**: unset `ERROR_REPORTING_DSN`; disable AI narrative
  (`AI_BAA_CONFIRMED=false` / remove key) if the AI path is implicated (ADR-0011/0021).
- **Isolate**: pull the affected instance from rotation (it fails `/readyz` or is drained)
  rather than killing it, to preserve state.
- **Secret compromise**: if `SECRET_STORE_KEY` may be exposed, treat all vaulted EMR tokens
  as compromised — plan revocation + re-authorization and key rotation (re-encryption
  migration; `backup-restore.md`). Rotate any exposed credential.
- **Preserve evidence**: snapshot logs and the audit table before remediation; do not edit
  the append-only audit log.

## 3. Assess PHI exposure

- Scope from the **audit log**: which patient records were read/written, by which actor, in
  the window (the log carries references + counts — enough to scope *what* and *whose*
  without exposing values).
- Confirm whether telemetry could have leaked PHI: by design it cannot (logs/metrics/error
  events are PHI-free and scrubbed — ADR-0018/0021). If a custom collector or a code
  regression is suspected, verify against the enforcement tests
  (`test_logging.py`, `test_metrics.py`, `test_errors.py`).
- **Breach determination (four-factor risk assessment) — [CE] + legal.** Whether an
  impermissible use/disclosure is a reportable breach is a covered-entity decision.

## 4. Notify (HIPAA timelines) — [CE]

All notifications are covered-entity + legal decisions. Reference timelines (confirm with
counsel — do not treat as legal advice):

- **Individuals** (§164.404): without unreasonable delay, **no later than 60 calendar days**
  after discovery.
- **HHS Secretary** (§164.408): ≥500 individuals affected → **within 60 days**; <500 →
  log and report annually (**within 60 days after year-end**).
- **Media** (§164.406): for a breach affecting **>500 residents of a state/jurisdiction**,
  notify prominent media without unreasonable delay, ≤60 days.
- **Business Associate → Covered Entity**: a BA notifies the CE without unreasonable delay,
  ≤60 days (relevant if the operator is a BA to another CE — [CE] to determine posture).

Maintain the notification record and content per the rule; legal owns wording and filing.

## 5. Remediate

- Fix the root cause; ship the fix with a **regression test** (repo rule — every bug fix
  ships a test; CLAUDE.md §7).
- Re-authorize/rotate any revoked credentials/tokens; restore service and return instances
  to rotation after `/readyz` is green.
- Verify data integrity from the append-only history (corrections are new records — ADR-0006);
  restore from a **verified** backup only if required (`backup-restore.md`, and remember the
  matching-era `SECRET_STORE_KEY`).

## 6. Post-mortem

- Blameless timeline: detection → containment → assessment → notification → remediation.
- Add any recurring failure class as a one-line preventive rule in `docs/lessons.md`
  (self-improvement rule, CLAUDE.md §8).
- Feed findings back into the risk analysis and update alert thresholds
  (`observability.md`) and this runbook.
- File an ADR if the incident forces a load-bearing design change.

## Quick reference — app levers

| Need | Lever |
|---|---|
| Invalidate all sessions | Rotate `JWT_SECRET` (ADR-0010) |
| Disable a principal | Per-operator deactivation (ADR-0019) |
| Stop AI egress | `AI_BAA_CONFIRMED=false` / remove `AI_API_KEY` (ADR-0011) |
| Stop error egress | Unset `ERROR_REPORTING_DSN` (ADR-0021) |
| Pull an instance safely | Drain / fail `/readyz` (503, PHI-free) — ADR-0018 |
| Scope what was accessed | Immutable audit log (reads + writes; references/counts) |
| Rotate token-vault key | Re-encryption migration + separate-key backup (`backup-restore.md`) |
