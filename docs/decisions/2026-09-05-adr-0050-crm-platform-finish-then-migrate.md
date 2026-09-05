# ADR-0050 — Agency CRM platform: finish on Workers, then migrate to Azure

- **Status:** Accepted
- **Date:** 2026-09-05
- **Decided by:** the owner (CLAUDE.md §8 — hosting and the ePHI boundary are owner-only;
  not self-authorized).
- **Relates to:** ADR-0018 (host-agnostic, secret-free deployment), the Azure estate in
  `infra/azure/main.bicep` + `.github/workflows/deploy.yml`,
  `docs/compliance/baa-inventory.md` row 3 (Azure) and row 6 (email providers),
  and `docs/brainstorm/2026-09-04-multi-tenant-wellness-platform-brainstorm.md`
  §2 (tenancy model), §28 (reuse table) and §29 D1 (repository/IP placement — still open).

## Context

The agency CRM — the tool for running the agency itself (clinics as tenants, contacts,
deals, campaigns, reorder reminders, social posting) — has been built in a **separate
repository** through PR #26. It runs on **Cloudflare Workers**, with **D1** (SQLite) as its
database and **R2** for backup objects.

This repository deploys on **Azure**, and does it properly: Container Apps for backend and
frontend, Azure Database for PostgreSQL Flexible Server, a migration Job that runs before
the apps roll, Log Analytics, images from ACR, and OIDC federated credentials so no
long-lived cloud secret sits in the repo. Application secrets are `@secure()` Bicep
parameters that land as Container Apps secrets.

Those two facts had not been put next to each other. Measured, on 2026-09-05:

| | CRM |
|---|---|
| Files importing `cloudflare:workers` | **46** |
| Files using `env.DB` (D1 / SQLite) | 23 |
| Files using `env.BACKUPS` (R2) | 2 |
| Tables in the frozen baseline migration | 19 |
| References to Azure or Postgres in source | **0** |

`cloudflare:workers`, D1 and R2 have no Azure equivalent that a binding swap reaches.
The baseline migration is SQLite DDL captured by dumping `sqlite_master`; on Postgres it is
a rewrite, not a port, and the tests that exercise it against `node:sqlite` go with it.

**The design doc and the code had been disagreeing.** The 2026-09-04 brainstorm in this
repo recommends *shared schema + `tenant_id` + Postgres Row-Level Security* (§2) and its
reuse table (§28) lists "Deployment, E2E harness, mobile shell — Unchanged", i.e. this
Azure path. The CRM was meanwhile being built on Workers and SQLite. Nobody reconciled
them, and secret-setting instructions were issued for a host the owner does not use.

### The data question

`reorder_reminders` carries `contact_id` into `contacts` (name, email, phone) alongside
`product_name`, `category` and `consent_at`. For a hormone or peptide clinic that is an
identified person's medication reorder schedule. `personal_interactions` holds free-text
notes about named people. Whatever the column names say, this behaves like PHI the moment
a real clinic uses it — and the CRM's host does not appear in
`docs/compliance/baa-inventory.md` at all.

The CRM has **never been deployed**, so no real data exists in it today. The exposure is
entirely about what happens at first sign-in.

## Options considered

- **(a) Port to Azure now.** One platform, one deploy, one compliance boundary. Costs the
  46-file binding rewrite and the Postgres schema rewrite before any further feature work.
- **(b) Stay on Workers permanently**, with a hard no-PHI line enforced in schema and
  review. Cheapest, but requires cutting or de-identifying `reorder_reminders`, and bets
  that clinics never put patient data in a clinic CRM.
- **(c) Extract a shared platform core** consumed by both (brainstorm §29 D1(c)). Best
  destination, but gated on an ADR-0001-level licensing question that is still open.
- **(d) Finish the CRM's feature work on Workers, then migrate to Azure.**

## Decision

**(d) — finish, then migrate.** The owner's call, 2026-09-05.

**With one binding constraint: no real patient or clinic data in the CRM until the
migration lands.** Synthetic data only. This is not a new rule — CLAUDE.md §5 already bars
real data from fixtures, tests, seeds and screenshots — it is that rule extended to the
deployed instance for the interim, and it is what makes (d) safe rather than merely
cheaper. The CRM may be stood up and signed into; it may not be given a real patient.

Option (c) remains the likely destination. This ADR settles *where the CRM runs*, not the
repository/IP/licence question, which is still owner-and-counsel work.

## Consequences

### Keeping the migration affordable

"Then migrate" is only a real plan if the surface that has to change stops growing. These
are already the house pattern; this ADR makes them explicit for the interim:

1. **Business logic stays in `lib/*.ts`, free of `cloudflare:workers`.** Already true of
   `backup-restore.ts`, `onboarding.ts`, `email-compliance.ts`, `preferences.ts`,
   `permissions.ts` and `slugify.ts` — that binding-freedom is why they are testable under
   `node --test`, and it is the same property that makes them portable. Route handlers stay
   thin: bindings in, pure functions do the work.
2. **New migrations avoid SQLite-only syntax where a portable form exists.** What will not
   port regardless: `AUTOINCREMENT`, and the baseline itself.
3. **Every new `env.DB` / `env.BACKUPS` site is a line item in the port.** The count is
   recorded above (23 + 2) so growth is visible rather than discovered at migration time.

### What the migration will cost when it is done

A third Container App in `main.bicep` alongside backend and frontend; the CRM's five
runtime secrets (`UNSUBSCRIBE_TOKEN_SECRET`, `RESEND_API_KEY`, `REMINDER_FROM_EMAIL`,
`CRON_SECRET`, `SOCIAL_TOKEN_ENCRYPTION_KEY`) becoming `@secure()` params and Container
Apps secrets, exactly as `jwt-secret` is today; D1 replaced by a database on the existing
Postgres Flexible Server; R2 replaced by Blob Storage; the 19-table baseline rewritten as
Postgres DDL with the backup/restore tests re-pointed; and the Workers cron replaced by a
Container Apps Job.

### Follow-ups this surfaces (owner)

Two entries in `docs/compliance/baa-inventory.md` are now behind the facts. They are named
here rather than edited, because that inventory scopes the neuropathy app and widening it
is its own decision:

- **No row exists for the CRM's current host.** Whatever runs the CRM is unattested. That
  is the mechanism behind this ADR's synthetic-data-only constraint.
- **Row 6 ("Email / notification providers") reads "Not implemented; no outbound email of
  PHI today."** The CRM sends via Resend, and the social publishing path reaches Meta,
  LinkedIn and X. Accurate for this app; no longer accurate across the estate.
