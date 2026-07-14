# Production deploy target — comparison & decision

> **Pricing/terms verified 2026-07-14 against the cited vendor pages — re-verify every
> figure and BAA term before purchase; vendors reprice and re-tier without notice.
> This document is not legal advice.** Whether a vendor's BAA is sufficient is a
> covered-entity + counsel determination (`docs/compliance/baa-inventory.md`). Selecting
> a host and **executing its BAA is the open prerequisite blocking any real PHI**
> (baa-inventory item 3 / open items).

Decision doc for **where to host the production backend**. Companion to ADR-0018 (which
deliberately drew the staging/production boundary and left the production host unchosen)
and to the host-agnostic runbooks in `docs/ops/` (`deployment.md`, `observability.md`,
`backup-restore.md`).

## What we are hosting (the workload)

From ADR-0018 / `docker-compose.yml` / `backend/Dockerfile`:

- **Backend**: one FastAPI container (Gunicorn + Uvicorn workers, port 8000, non-root,
  secret-free image). Config is 100% environment variables; several are **SECRET**
  (`JWT_SECRET`, `SECRET_STORE_KEY`, `OPS_BOOTSTRAP_TOKEN`, `DATABASE_URL`) and must come
  from a secret store in production (`docs/ops/deployment.md`).
- **Frontend**: one non-root nginx container serving the SPA and reverse-proxying the API
  (same-origin default, port 8080).
- **Postgres 16**: **PHI at rest** — the database is the PHI store; disk/database
  encryption at rest and TLS in transit are hosting-layer duties
  (`docs/compliance/hipaa-ops-checklist.md`, §164.312 rows + "Honest gaps").
- **Migrations before boot**: a one-shot `alembic upgrade head` run with the same backend
  image, gated before the app starts.
- **Observability**: `GET /metrics` is Prometheus-scrapable (PHI-free by construction,
  ADR-0021); scrape must stay on an internal network (`docs/ops/observability.md`).
- **Backups**: `pg_dump`-based, with the tested drill `scripts/pg_backup_drill.sh`
  (ADR-0021) and the `SECRET_STORE_KEY`-backed-up-separately rule
  (`docs/ops/backup-restore.md`).

## Constraints the target must satisfy

| Constraint | Source |
|---|---|
| Vendor **signs a BAA** before any real PHI touches it | `baa-inventory.md` item 3 — hard gate |
| **Solo owner** operates it — low, well-runbooked ops burden | project reality; CLAUDE.md §8 autonomous loop |
| **Pilot scale**: 1 small app node + 1 Postgres + backups; cost matters | roadmap stage |
| Encrypted storage at rest, TLS termination in front of the app | `hipaa-ops-checklist.md` §164.312 |
| Secrets injected from a managed store, never baked/committed | CLAUDE.md §5; ADR-0018 |
| Existing docker-compose topology + runbooks should carry over with minimal rework | ADR-0018; `docs/ops/*` |
| Internal-only Prometheus scrape of `/metrics` | ADR-0021; `observability.md` |

---

## Option 1 — AWS: EC2 (docker-compose) + RDS Postgres, BAA via AWS Artifact

**Shape.** One small EC2 instance runs our existing compose file (minus the `db`
service); **RDS for PostgreSQL** replaces the compose Postgres (managed, encrypted at
rest, automated snapshots); an **Application Load Balancer + ACM certificate** terminates
TLS in front of the frontend nginx. ECS/Fargate is the "grown-up" alternative shape, but
for a solo-owner pilot the EC2-with-compose shape reuses ADR-0018's topology nearly
verbatim; ECS is the later scale-out path, not the pilot.

**BAA — VERIFIED (self-serve, $0).** AWS offers a self-service **Business Associate
Addendum accepted online in AWS Artifact** under the standard account agreement — no
sales call, no fee, effective immediately on acceptance; accepting at the AWS
Organizations level covers all member accounts. The BAA applies only while PHI is kept to
**HIPAA-eligible services** with required configurations.
Sources: <https://aws.amazon.com/compliance/hipaa-compliance/>,
<https://docs.aws.amazon.com/artifact/latest/ug/managing-agreements.html>,
<https://aws.amazon.com/blogs/security/accept-a-baa-with-aws-for-all-accounts-in-your-organization/>.

**HIPAA-eligible services we would use** (all confirmed on
<https://aws.amazon.com/compliance/hipaa-eligible-services-reference/>): EC2, RDS
(PostgreSQL), Elastic Load Balancing, S3 (encrypted dump/artifact storage), Secrets
Manager, CloudWatch, ECR (image registry), AWS Backup. (Fargate is eligible too — ECS/EKS
engines — if we later move off the single node.)

**Estimated monthly cost (pilot, us-east-1, on-demand — ESTIMATE, size via the AWS
calculator before purchase):**

| Item | Est. / month |
|---|---|
| EC2 `t4g.small` (2 vCPU / 2 GB) app node | ~$12 |
| EBS gp3 30 GB | ~$3 |
| RDS PostgreSQL `db.t4g.micro`–`small`, single-AZ | ~$12–25 |
| RDS storage 20 GB gp3 + automated backups (free up to DB size) | ~$3 |
| ALB (base + light LCU) + ACM cert (free) | ~$17–22 |
| S3 dumps, Secrets Manager (~4 secrets), CloudWatch, egress | ~$5–10 |
| **Total** | **~$55–110 / month** |

Third-party trackers put `db.t4g.micro` between ~$12 and ~$22/mo depending on date/config
(<https://instances.vantage.sh/aws/rds/db.t4g.micro>,
<https://aws.amazon.com/rds/postgresql/pricing/>) — **UNVERIFIED at the exact-cent level;
price with the official calculator**. Multi-AZ RDS roughly doubles the DB line; not
needed at pilot.

**Repo changes.** Small and additive: a `docker-compose.prod.yml` override (drop `db` +
`migrate`-against-local, point `DATABASE_URL` at the RDS endpoint, remove published DB
port), a bootstrap script (VPC/SG, instance, ALB + ACM), and a secret-injection step
(SSM Parameter Store / Secrets Manager → env at deploy — never a committed `.env`). TLS
terminates at the ALB (ACM-managed renewal); nginx stays HTTP behind it, matching the
"app speaks HTTP behind a TLS-terminating gateway" posture in `hipaa-ops-checklist.md`.
`/metrics`: run Prometheus as a sidecar container on the node (internal network) — no
public exposure. Backups: RDS automated snapshots **plus** keep `pg_backup_drill.sh`
pointed at the RDS endpoint on a schedule (a snapshot is not a tested restore).

**Operational burden.** Highest of the three: we patch the instance OS + Docker engine,
rotate the node, and own single-node availability (no HA; acceptable at pilot — RDS
handles DB durability). Runbooks (`deployment.md`, `backup-restore.md`) apply almost
unchanged.

**Lock-in.** Low–moderate. RDS is vanilla Postgres (`pg_dump` out any time); the compose
file stays portable; only the bootstrap scripts and secret wiring are AWS-shaped.

---

## Option 2 — Managed PaaS that signs a BAA: **Aptible** (most credible), field survey below

Who actually signs a BAA today, verified 2026-07-14:

| Vendor | BAA today? | Tier required | Verified? |
|---|---|---|---|
| **Aptible** | Yes — HIPAA is the product; dedicated stack, HIPAA controls enforced by default | **Production plan, $499/mo base + usage** (app containers/DB/storage metered on top; their example shows ~$60/mo per small container/DB) | VERIFIED — <https://www.aptible.com/pricing>, <https://www.aptible.com/docs/core-concepts/security-compliance/compliance-frameworks/hipaa> |
| Render | Yes — HIPAA-enabled workspace; dashboard flow then Render emails a BAA signing link; **+20% surcharge on all usage** in the HIPAA workspace; enablement irreversible | **Scale plan ($499/mo flat, per Apr 2026 repricing) or Enterprise** | VERIFIED — <https://render.com/docs/hipaa-compliance>, <https://render.com/docs/new-workspace-plans> |
| Fly.io | Yes — pre-signed BAA requested from the dashboard compliance page | **Compliance Package, $99/mo** add-on ("everything you need for HIPAA-compliant workloads, from BAAs to SOC2s"); machines ~$6–12/mo, Managed Postgres Basic ~$38/mo + $0.28/GB | VERIFIED for the add-on price — <https://fly.io/pricing/>, <https://fly.io/docs/blueprints/going-to-production-with-healthcare-apps/>. **UNVERIFIED: whether Managed Postgres is inside BAA scope** (docs don't enumerate covered services; confirm with sales in writing) |
| Railway | Enterprise-only, on request | reported **~$1,000/mo minimum commitment** | **UNVERIFIED** (behind sales) — <https://docs.railway.com/enterprise/compliance>, <https://station.railway.com/feedback/hipaa-baa-pricing-vs-render-0b643cdf> |

**Pick: Aptible.** It is the most credible BAA counterparty in this class — HIPAA hosting
is its entire business, the BAA covers every service on the dedicated stack, and HIPAA
controls (encryption at rest, network isolation, audited access) are enforced by default
rather than assembled by us. Fly.io is the budget path (~$150/mo all-in) but its HIPAA
offering is a young add-on with unenumerated BAA scope; Render's HIPAA workspace now
effectively costs the same as Aptible ($499 flat + 20% surcharge) with less compliance
depth; Railway prices itself out at pilot scale.

**Estimated monthly cost (pilot).** $499 base + ~$60 app container + ~$60 managed
Postgres + ~$2 storage ≈ **~$620/month** (calculator figures on their pricing page;
usage rates are examples — **re-verify in the calculator**). Backups and encrypted
storage are included in the managed DB.

**Repo changes.** Compose is not used: Aptible deploys the Dockerfile directly
(`git push`/`aptible deploy`), so we keep both Dockerfiles as-is, add an app + managed-DB
definition, and drop the `db`/`migrate` compose services (migration one-shot becomes an
`aptible` before-release command or manual `alembic upgrade head` run — same image, same
rule). Secrets go into Aptible's config store (`aptible config:set`). TLS termination is
a managed endpoint (their edge). `/metrics`: no in-VPC Prometheus of our own without
extra work — scrape via an internal endpoint or fall back to their metric drains
(**UNVERIFIED fit** for our Prometheus rules; check before committing).
`pg_backup_drill.sh` still works against a DB tunnel (`aptible db:tunnel`).

**Operational burden.** Lowest: no OS patching, managed DB with automatic backups,
platform handles HA plumbing. **Lock-in.** Moderate: Postgres exports cleanly, but deploy
workflow, secret store, TLS endpoints, and drains are platform-specific.

---

## Option 3 — HIPAA-focused managed VPS: Atlantic.Net HIPAA hosting

**Shape.** Their smallest HIPAA plan is a managed Linux VM (6 vCPU / 16 GB / 200 GB SSD —
generously oversized for our pilot) behind a managed FortiGate firewall, with daily
onsite + offsite backups, managed VPN + MFA access, IPS, vulnerability scans, and a
**signed BAA included in all HIPAA plans**. We run our `docker-compose.yml` nearly as-is
(including the Postgres container) on the VM.

**BAA — VERIFIED (included).** BAA ships with every HIPAA hosting plan.
Source: <https://www.atlantic.net/hipaa-compliant-hosting/>.

**Cost.** Linux "HIPAA Developer" listed at **$552.31/month** (Business $644.16; DR
$973.27) as of 2026-07-14 on the page above. Third-party roundups quote lower entry
points ($320–$410) for older/negotiated configurations — **UNVERIFIED; custom quotes are
behind sales (sales@atlantic.net)**.

**Repo changes.** Fewest of all: compose runs as-is (keep the `db` service on the VM's
encrypted storage), add a TLS terminator in front of nginx (either their load balancer or
a Caddy/certbot container we add to compose), inject secrets via a root-only env file on
the managed VM (no managed secret store — weaker than options 1–2), run Prometheus as a
compose sidecar, and schedule `pg_backup_drill.sh` on the VM in addition to their
daily managed backups.

**Operational burden.** Mixed: Atlantic.Net manages the perimeter (firewall, IPS,
backups, VPN, scanning) but **we still own the OS/app stack on the VM** — Docker
patching, Postgres upgrades (it's our container, not a managed DB), and single-VM
availability. **Lock-in.** Lowest technically (it's a VM + compose), but the price never
drops with usage, and we'd pay ~$550/mo for hardware we use a fraction of.

---

## Side-by-side

| | 1. AWS EC2 + RDS | 2. Aptible (PaaS) | 3. Atlantic.Net (HIPAA VPS) |
|---|---|---|---|
| Est. monthly (pilot) | **~$55–110** (est.) | ~$620 | ~$552 (listed) |
| BAA | Self-serve in AWS Artifact, $0, standard account agreement — **VERIFIED** | Signed on Production plan ($499/mo) — **VERIFIED** | Included in all HIPAA plans — **VERIFIED** |
| Repo diff | compose override + bootstrap scripts + SSM secrets | drop compose; platform app/DB config | nearly none (add TLS container) |
| Managed Postgres / backups | RDS: encrypted, snapshots (keep drill) | managed DB + backups included | our container; their VM backups + drill |
| TLS | ALB + ACM (auto-renew) | platform endpoint | their LB or our Caddy/certbot |
| Secrets | Secrets Manager / SSM | platform config store | env file on managed VM (weakest) |
| `/metrics` scrape | Prometheus sidecar, internal SG | drains / internal endpoint (**fit UNVERIFIED**) | Prometheus sidecar on VM |
| Ops burden | highest (OS + node) | lowest | middle (perimeter managed, stack ours) |
| Lock-in | low–moderate | moderate | lowest |

## Recommendation — **AWS EC2 + RDS Postgres (Option 1)**

Primary pick, tied to our constraints:

1. **BAA mandatory before real PHI** → AWS is the only option where the BAA is
   self-serve, immediate, and $0 under the standard account agreement (Artifact) — the
   gating open item in `baa-inventory.md` closes on day one with no sales cycle.
2. **Pilot scale + solo owner economics** → ~$55–110/mo vs ~$550–620/mo for options 2–3;
   at pilot traffic the 6–10× premium buys convenience we don't need yet.
3. **Existing docker-compose + runbooks** → the ADR-0018 topology survives nearly
   unchanged (compose on one node, RDS instead of the `db` service);
   `deployment.md`/`backup-restore.md`/`pg_backup_drill.sh` all apply as written.
4. **PHI posture** → RDS gives encrypted-at-rest managed Postgres + automated snapshots;
   ALB + ACM gives TLS with managed renewal; Secrets Manager/SSM satisfies the
   "secret manager, never the repo" rule (CLAUDE.md §5).

Trade-off accepted: we own OS patching and single-node availability. At pilot scale that
is a bounded, runbookable chore; the exit ramps (ECS/Fargate on the same BAA, or Aptible
if ops burden ever outgrows a solo owner) stay open because the images and Postgres are
portable.

**Next implementation portion — "deploy portion: infra scripts + runbook for AWS EC2 +
RDS"**: `scripts/` bootstrap (VPC/SG/EC2/ALB+ACM/RDS, idempotent), a
`docker-compose.prod.yml` override (external DB, no published DB port), SSM/Secrets
Manager secret injection at deploy, Prometheus sidecar scrape wiring, RDS
snapshot + scheduled `pg_backup_drill.sh`, and `docs/ops/deploy-aws.md` (+ ADR + roadmap
update per Definition of Done).

## "Not before" — gates on real-PHI go-live

No real PHI enters the system until **every** box below is checked
(cross-references: `docs/compliance/baa-inventory.md` open items,
`docs/compliance/hipaa-ops-checklist.md` honest gaps, `docs/ops/backup-restore.md`):

- [ ] **AWS BAA accepted in AWS Artifact** (org-level), and recorded in
      `baa-inventory.md` item 3 (flips from "not yet chosen").
- [ ] **PHI kept to HIPAA-eligible services only**, configured per the BAA (RDS + EBS
      encryption at rest ON; no PHI in S3 buckets without encryption + access logging).
- [ ] **TLS live end-to-end** (ALB + ACM in front of nginx) — closes the §164.312
      encryption-in-transit [CE] gap.
- [ ] **Secrets in Secrets Manager/SSM** (`JWT_SECRET`, `SECRET_STORE_KEY`,
      `OPS_BOOTSTRAP_TOKEN`, `DATABASE_URL`), injected at deploy; no `.env` in any image
      or repo; `SECRET_STORE_KEY` backed up **separately from the database**
      (`backup-restore.md` trap).
- [ ] **Backup drill scheduled and first drill recorded** — `pg_backup_drill.sh` against
      the RDS endpoint plus the full end-to-end drill (restore + matching-era key +
      `/readyz` + synthetic read-back).
- [ ] **`/metrics` and error reporting stay internal** — Prometheus on the private
      network only; `ERROR_REPORTING_DSN` self-hosted or BAA-covered, else unset
      (baa-inventory items 4–5).
- [ ] **Remaining [CE] checklist items dispositioned** (`hipaa-ops-checklist.md`):
      security risk analysis, RPO/RTO targets, automatic-logoff policy, emergency-access
      procedure, incident-response contacts filled in.
- [ ] **Anthropic narration stays OFF** (`AI_BAA_CONFIRMED` unset) until that separate
      BAA is executed (baa-inventory item 1).

## Sources (accessed 2026-07-14)

- AWS HIPAA program & BAA: <https://aws.amazon.com/compliance/hipaa-compliance/> ·
  <https://docs.aws.amazon.com/artifact/latest/ug/managing-agreements.html> ·
  <https://aws.amazon.com/blogs/security/accept-a-baa-with-aws-for-all-accounts-in-your-organization/>
- AWS HIPAA-eligible services: <https://aws.amazon.com/compliance/hipaa-eligible-services-reference/>
- AWS pricing (estimates): <https://aws.amazon.com/rds/postgresql/pricing/> ·
  <https://instances.vantage.sh/aws/rds/db.t4g.micro>
- Aptible: <https://www.aptible.com/pricing> ·
  <https://www.aptible.com/docs/core-concepts/security-compliance/compliance-frameworks/hipaa>
- Render: <https://render.com/docs/hipaa-compliance> · <https://render.com/docs/new-workspace-plans>
- Fly.io: <https://fly.io/pricing/> · <https://fly.io/docs/about/healthcare/> ·
  <https://fly.io/docs/blueprints/going-to-production-with-healthcare-apps/> ·
  <https://fly.io/docs/about/pricing/>
- Railway (UNVERIFIED tier terms): <https://docs.railway.com/enterprise/compliance> ·
  <https://station.railway.com/feedback/hipaa-baa-pricing-vs-render-0b643cdf>
- Atlantic.Net: <https://www.atlantic.net/hipaa-compliant-hosting/>

### UNVERIFIED items (re-check before purchase)

- Exact AWS instance/ALB/RDS rates (estimated from published on-demand pages/trackers;
  price with the official AWS calculator).
- Fly.io: whether **Managed Postgres is within BAA scope** (get it in writing).
- Railway's Enterprise minimum commitment (~$1,000/mo reported; behind sales).
- Aptible per-resource usage rates beyond the pricing-page calculator examples.
- Atlantic.Net sub-$552 entry pricing quoted by third-party roundups (custom quotes
  behind sales).
