# HIPAA Security Rule — operational checklist

A practical, honest mapping of the HIPAA Security Rule to **what this application actually
does** today, with gaps flagged. Recorded under **ADR-0021**.

> **This is not legal advice and not a compliance attestation.** HIPAA compliance is a
> property of the **covered entity's** whole environment (policies, workforce training,
> physical safeguards, executed BAAs, risk analysis), not of an application alone. This
> checklist covers only the safeguards the *software* implements or enables; items marked
> **[CE]** must be completed by the covered entity and its counsel. The app is built for
> **BioMech Health** as licensee; IP/ownership per ADR-0001.

Legend: ✅ implemented in-app · ◑ partial / enabling only · ☐ **[CE]** covered-entity duty.

## Administrative safeguards (§164.308)

| Requirement | Status | What the app does / the gap |
|---|---|---|
| Security risk analysis & management | ☐ [CE] | Org-level process. The app's ADRs (0011/0017/0018/0021) document its threat decisions as inputs. |
| Workforce security / termination | ◑ | App-side: per-operator ops accounts + per-operator **deactivation** (ADR-0019); a deactivated principal of any role is refused at authentication within the access-token TTL. Org offboarding process is **[CE]**. |
| Information access management (least privilege) | ✅ | Role gates (patient/clinician/ops); per-record isolation; clinician panel is **consent-scoped** with a neutral 404-over-403 posture (ADR-0012/0020). |
| Security awareness / training | ☐ [CE] | Organizational. |
| Security incident procedures | ✅◑ | Runbook shipped: `incident-response-runbook.md`. Detection signals (alerts + audit log) are app-provided; declaration/notification decisions are **[CE]**. |
| Contingency plan (backup, DR) | ◑ | Backup/restore + **tested** verification drill (`backup-restore.md`, `scripts/pg_backup_drill.sh`). RPO/RTO targets and offsite DR are **[CE]**. |
| Business Associate Agreements | ◑ [CE] | App **gates** PHI-to-third-party flows (AI narrative off until BAA attested — ADR-0011; error/metrics collector must be self-hosted or BAA-covered — ADR-0021). Executing BAAs is **[CE]**. See `baa-inventory.md`. |
| Evaluation (periodic) | ☐ [CE] | Organizational, ongoing. |

## Physical safeguards (§164.310)

| Requirement | Status | Notes |
|---|---|---|
| Facility access, workstation, device/media controls | ☐ [CE] | Hosting/data-center and endpoint controls are owned by the covered entity and its cloud provider (chosen later; must be BAA-covered — `baa-inventory.md`). |
| Media disposal / re-use | ◑ [CE] | App enforces backup retention/destruction guidance (`backup-restore.md`); execution and physical media disposal are **[CE]**. |

## Technical safeguards (§164.312)

| Requirement | Status | What the app does / the gap |
|---|---|---|
| Access control — unique user ID | ✅ | Every principal is a unique account (patient/clinician/ops); JWT-based auth (ADR-0010/0019). |
| Access control — emergency access | ☐ [CE] | Break-glass procedure is an org decision. |
| Automatic logoff | ◑ | Short-lived access tokens with refresh (ADR-0010); UI/session inactivity timeout is a client/[CE] policy. |
| Encryption at rest | ✅◑ | EMR OAuth tokens encrypted at rest in the DB token vault (Fernet, fail-closed — ADR-0017). **Full-database/disk encryption is a hosting concern [CE]** (enable at the storage layer). |
| Encryption in transit | ◑ [CE] | App speaks HTTP behind a TLS-terminating gateway; **TLS is deployed by the covered entity** (ADR-0018 draws the staging/prod boundary — staging has no TLS). |
| Audit controls | ✅ | **Audit logging on PHI reads AND writes**, values never logged — counts/references only (CLAUDE.md §5; ADR-0012/0014/0017). Structured request logs and metrics are **PHI-free by construction** (ADR-0018/0021). |
| Integrity (ALCOA+, tamper-evidence) | ✅ | Research-grade, append-only/immutable data with corrections-as-new-records and full provenance (ADR-0006). |
| Person/entity authentication | ✅ | Argon2id password hashing; bearer JWT; revocation enforced centrally (ADR-0017/0019). |
| Transmission security | ◑ | PHI-to-third-party egress is gated (BAA/self-hosted); in-transit TLS is **[CE]** (above). |

## Breach notification readiness (§164.400–414)

| Item | Status | Notes |
|---|---|---|
| Detect | ✅ | Alerts (`observability.md`) + immutable audit log surface anomalies. |
| Assess PHI exposure | ◑ | Audit log enables scoping *what* was accessed; the four-factor risk assessment is **[CE]**. |
| Notify within HIPAA timelines | ☐ [CE] | Individuals/HHS/media notifications per §164.404–408 are covered-entity + legal decisions. See `incident-response-runbook.md`. |

## Honest gaps (as of this portion)

- **TLS in transit** and **full-disk/database encryption at rest** are hosting-layer duties
  the covered entity must enable; the app assumes a TLS-terminating gateway (ADR-0018).
- **No cloud provider chosen yet** — its BAA is a prerequisite before any real PHI
  (`baa-inventory.md`).
- **Error-reporting/metrics collector**: the app makes them PHI-free and self-hostable, but
  if a collector is deployed it must be self-hosted or BAA-covered — the app cannot enforce
  where the operator points `ERROR_REPORTING_DSN` beyond keeping the payload scrubbed.
- **Automatic logoff / emergency access / DR targets (RPO/RTO)** are policy decisions not
  yet set by the covered entity.
- This app is **pre-production**; no real PHI exists yet, and several controls above are
  *enabling* (◑) rather than *operating*.
