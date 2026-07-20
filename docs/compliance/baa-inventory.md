# Business Associate (BAA) inventory

Every third party that **could** receive Protected Health Information (PHI) from this
application, and its Business Associate Agreement status. Recorded under **ADR-0021**.

> **Not legal advice.** Whether a party is a Business Associate, and whether a signed BAA is
> in place, are determinations for the **covered entity** (BioMech Health as licensee /
> operator) and its counsel. This inventory tracks the *technical* PHI-flow surface the app
> exposes and the **gates** the app enforces before PHI can leave it. Executing BAAs is a
> covered-entity duty — the app will not send PHI to an unattested party, but it cannot
> execute an agreement.

Legend: **Gated OFF** = app blocks the flow until the covered entity attests/configures ·
**Patient-authorized** = flow authorized per-patient via OAuth consent · **[CE]** = covered
entity must execute the BAA before real PHI.

## Inventory

| # | Third party | PHI it could receive | App gate | BAA status |
|---|---|---|---|---|
| 1 | **Anthropic** (AI narrative — ADR-0011) | The model receives only the **computed Trajectory** (direction, summary, signals) it may rephrase — never raw observations or documents. Still treat as potential PHI. | **Gated OFF by default**: narration runs only with an API key **AND** explicit `AI_BAA_CONFIRMED` operator attestation (ADR-0011); the LLM is never in the request path. Disclosures are audited + counted by type (PHI-free — ADR-0021). | ☐ **[CE]** — must execute a BAA with Anthropic and set the attestation before enabling. Off until then. |
| 2 | **EMR / EHR providers** (SMART on FHIR — ADR-0008/0009, e.g. Epic, Cerner/Oracle Health) | Inbound: patient clinical observations pulled from the EMR. The app is the recipient here; the direction of concern is the patient authorizing the app. | **Patient-authorized** per connection via SMART OAuth; tokens encrypted at rest, revocable, deleted on revoke/re-link (ADR-0017). | Patient-authorized data access, not a classic outbound-PHI BA relationship; **[CE]** to confirm each provider's terms/registration (Wave 3 enrollment). |
| 3 | **Microsoft Azure** (hosting — chosen 2026-07-18) | Everything — it stores and runs the database (PHI at rest) and the app. In-scope services: **Azure Container Apps**, **Azure Database for PostgreSQL Flexible Server**, **Azure Monitor / Log Analytics** (logs are engineered PHI-free per ADR-0018 §4, but the workspace is still in scope). | App is host-agnostic and secret-free (ADR-0018); Postgres uses `?ssl=require` in transit; provider-level disk encryption at rest. Currently a **synthetic-data-only staging** deployment (`neuropathy-rg2`, eastus2). | ☐ **[CE]** — **prerequisite before any real PHI.** For Azure the HIPAA BAA is generally incorporated in the **Microsoft Product Terms / Data Protection Addendum (DPA)** that comes with the Azure agreement (no separate signature for most agreement types); the covered entity + counsel must **confirm the DPA applies to the subscription and covers the three services above**, and document it. See deploy-azure.md §0. |
| 4 | **Error-reporting collector** (error seam — ADR-0021) | Only a **PHI-scrubbed** event (exception *type*, route template, request id, status, timestamp). The exception message, query, body, headers, and patient data are **never** sent. | **Gated OFF by default** (`ERROR_REPORTING_DSN` unset). When set, the payload is scrubbed by construction and the destination must be self-hosted or BAA-covered. | ☐ **[CE]** — if a collector is used, it must be **self-hosted** (no BA) or a **BAA-covered** service. App keeps the payload scrubbed regardless. |
| 5 | **Metrics / monitoring collector** (Prometheus scraper — ADR-0021) | `GET /metrics` is **PHI-free by construction** (route templates + aggregate counters). No PHI flows even if scraped. | Metrics carry no PHI; scrape on the internal network. | Low risk — no PHI in the payload. **[CE]** to keep the endpoint off public ingress and, if a managed monitoring SaaS ingests it, confirm terms. |
| 6 | **Email / notification providers** (future) | Any address/notification content, if added later. | Not implemented; no outbound email of PHI today. | ☐ **[CE]** — evaluate + BAA when/if notifications are built. |

## Standing rules (app-enforced)

- **No PHI leaves the app to an unattested third party.** Anthropic narration and the error
  collector are **off by default**; each requires an explicit operator action (BAA
  attestation / self-hosted DSN) to enable.
- **Telemetry is PHI-free by construction** (logs, metrics, error events — ADR-0018/0021),
  so the observability stack is not a PHI-flow surface as long as it stays scrubbed.
- **Any new outbound integration** that could carry PHI must be added to this inventory,
  gated (off until configured), and cannot ship enabled without a covered-entity BAA sign-off
  (CLAUDE.md §5; autonomous-operation guardrails — STOP for a BAA).

## Open items (covered entity)

- [x] Select a hosting/cloud provider — **Azure** (2026-07-18); staging is live with synthetic data.
- [ ] Confirm the **Microsoft Azure DPA/BAA** applies to the subscription and covers Container Apps + PostgreSQL Flexible Server + Azure Monitor, and document it (blocks real PHI — deploy-azure.md §0).
- [ ] Execute the Anthropic BAA and set `AI_BAA_CONFIRMED` before enabling AI narrative.
- [ ] Decide the error-reporting collector (self-hosted vs BAA-covered) or leave it off.
- [ ] Confirm each EMR provider's registration/terms during Wave 3 enrollment.
