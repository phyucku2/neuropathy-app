# Deploy runbook — Azure (Container Apps + PostgreSQL Flexible Server)

This is the Azure path for standing up the **real** neuropathy-app (FastAPI backend +
managed Postgres + the SPA pointed at it), parallel to the Render blueprint in
`render.yaml` / `docs/ops/DEPLOY.md`. Same two container images, same env contract, same
release step (`alembic upgrade head` before the server serves) — only the platform
changes. The Bicep template is `infra/azure/main.bicep`.

> Companion docs: `docs/ops/DEPLOY.md` (Render + vendor-neutral), `docs/ops/deployment.md`
> (host-agnostic image contract + full env table), `docs/ops/backup-restore.md`,
> `docs/ops/observability.md`. Architecture: ADR-0018 (topology), ADR-0010/0017 (secrets),
> ADR-0021 (server/metrics), ADR-0011 (AI narrative).

---

## 0. HIPAA / PHI — read this first

- **Azure is HIPAA-eligible, but you MUST have a signed BAA with Microsoft covering these
  services BEFORE any real PHI flows.** For most enterprise agreements the BAA is part of
  the **Microsoft Product Terms / Data Protection Addendum (DPA)**; confirm it explicitly
  lists **Azure Container Apps**, **Azure Database for PostgreSQL Flexible Server**, and
  **Azure Monitor / Log Analytics** (this template ships app logs to Log Analytics — logs
  are engineered PHI-free per ADR-0018 §4, but the workspace is still in scope). This is a
  **covered-entity action** (`docs/compliance/baa-inventory.md`); the app cannot execute it.
- Until the BAA is in place, deploy only with **synthetic / test data**.
- The app is engineered to keep every PHI-to-third-party seam **OFF by default** (AI
  narrative gated behind a BAA attestation — see §8; error/metrics collector self-hosted or
  BAA-covered — ADR-0021). Azure hosting does not change that posture.
- **Provisioning uses your own Azure subscription + billing.** Nothing here creates
  resources on its own, and **no secrets are committed** — every credential is a `@secure()`
  parameter you supply at deploy time (§4) or a value the template generates into a
  Container Apps *secret* (never into git, never into a template output).

---

## 1. What gets deployed

`infra/azure/main.bicep` provisions, into one resource group:

| Resource | Type | Notes |
|---|---|---|
| Log Analytics workspace | `Microsoft.OperationalInsights/workspaces` | Required by the Container Apps environment for app logs. |
| Container Apps environment | `Microsoft.App/managedEnvironments` | The shared runtime + internal DNS for the two apps and the job. |
| **Backend** app | `Microsoft.App/containerApps` | From `backend/Dockerfile`. **Internal** ingress on `:8000`. Liveness `/healthz`, readiness `/readyz`. Not internet-exposed. |
| **Frontend** app | `Microsoft.App/containerApps` | From `frontend/Dockerfile`. **External** ingress on `:8080`. Reverse-proxies the API to the backend (same-origin → no CORS). |
| **Migration** job | `Microsoft.App/jobs` | Manual-trigger job running `alembic upgrade head` on the **same backend image**. See §6. |
| PostgreSQL | `Microsoft.DBforPostgreSQL/flexibleServers` (+ `databases`, `firewallRules`) | Managed Postgres; a database; an "allow Azure services" firewall rule. |

```
  browser ──HTTPS──> frontend container app (nginx, external ingress)
                        │  reverse-proxies /auth, /observations, /trajectory, ...
                        ▼  (internal environment DNS, BACKEND_ORIGIN)
                     backend container app (gunicorn, internal ingress) ──async(TLS)──> PostgreSQL Flexible Server
                     migration job (alembic upgrade head)  ────────────────────────────┘  (run before serving)
```

The backend never migrates its own schema (files-only rule); `docker-entrypoint.sh` does
not migrate on boot, so running migrations only in the job means **no double-run** (same as
Render's release phase).

---

## 2. Prerequisites

- An **Azure subscription** with billing, and the **BAA** situation in §0 understood.
- **Azure CLI** (`az`) ≥ 2.53 with the Container Apps extension:
  ```bash
  az login
  az account set --subscription "<SUBSCRIPTION_ID_OR_NAME>"
  az extension add --name containerapp --upgrade
  az provider register --namespace Microsoft.App
  az provider register --namespace Microsoft.OperationalInsights
  az provider register --namespace Microsoft.DBforPostgreSQL
  ```
- A **container registry** the environment can pull from. The recommended path is **Azure
  Container Registry (ACR)**. The images are built from this repo's `backend/` and
  `frontend/` Dockerfiles.

### 2.1 Build and push the two images

Do **not** run a real `docker build` as part of this runbook's dry-run; when you are ready
to deploy:

```bash
RG=neuropathy-rg
LOC=eastus
ACR=neuroacr$RANDOM          # must be globally unique, lowercase alphanumerics
TAG=$(date +%Y%m%d-%H%M)

az group create -n "$RG" -l "$LOC"
az acr create -n "$ACR" -g "$RG" --sku Basic --admin-enabled true

# Build in ACR (no local Docker needed). Context is each app's subdirectory.
az acr build -r "$ACR" -t "neuropathy-backend:$TAG"  -f backend/Dockerfile  backend
az acr build -r "$ACR" -t "neuropathy-frontend:$TAG" -f frontend/Dockerfile frontend

ACR_SERVER=$(az acr show -n "$ACR" -g "$RG" --query loginServer -o tsv)
ACR_USER=$(az acr credential show -n "$ACR" -g "$RG" --query username -o tsv)
ACR_PASS=$(az acr credential show -n "$ACR" -g "$RG" --query 'passwords[0].value' -o tsv)
```

(If your images already live on a **public** registry, leave `registryServer` blank in §5
and skip the ACR credential params — the template omits the registry block when the server
is blank.)

---

## 3. Environment variables — who sets what

Confirmed against `backend/app/core/config.py`, `backend/gunicorn.conf.py`,
`backend/app/api/routes/health.py`.

**Operator supplies (secure params → Container Apps secrets, never in git):**

| Var | Param | Required? | How |
|---|---|---|---|
| `JWT_SECRET` | `jwtSecret` | **Required** (durable auth, ADR-0010) | `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Rotating it logs everyone out. |
| Postgres admin password | `postgresAdminPassword` | **Required** | Strong password; feeds the built `DATABASE_URL`. |
| `SECRET_STORE_KEY` | `secretStoreKey` | Optional* | Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. |
| `OPS_BOOTSTRAP_TOKEN` | `opsBootstrapToken` | Optional** | `python -c "import secrets; print(secrets.token_urlsafe(48))"` (≥ 32 chars). |
| `DATABASE_URL` | `databaseUrlOverride` | Optional | Blank = **built for you** from the Postgres server (§5.1). Set only to manage the string yourself. |
| Registry password | `registryPassword` | Only if private registry | ACR password/token from §2.1. |

**Template sets / generates (you do nothing):**

| Var | Source |
|---|---|
| `DATABASE_URL` | Built as `postgresql+asyncpg://…?ssl=require` from the provisioned server (§5.1), unless you pass `databaseUrlOverride`. |
| `APP_ENV=production`, `APP_DEBUG=false` | Fixed in the Bicep. |
| `WEB_CONCURRENCY` | `webConcurrency` param (default `2`). Size to backend CPU. |
| `PORT=8000` | Set to match backend ingress `targetPort` (gunicorn honors `$PORT`). |
| `API_BASE_URL=""` + `BACKEND_ORIGIN` (frontend) | Wired to the backend's internal FQDN (§7). |

\* `SECRET_STORE_KEY` — leave blank for basic register/login/check-in; it only encrypts the
DB-backed **EMR OAuth token vault** (ADR-0017). Blank = those tokens stay in a per-process
in-memory vault (fail closed — never written to the DB in plaintext). **If you set it, back
it up separately from the database** (`docs/ops/backup-restore.md`) — losing it makes stored
EMR tokens undecryptable. When blank, the template omits the secret **and** its env var
entirely (config.py treats absent exactly as blank).

\*\* `OPS_BOOTSTRAP_TOKEN` — leave blank unless you need to provision **clinician** accounts.
Blank disables provisioning (patient register/login unaffected). If set it must be ≥ 32
chars or the backend **fails closed at startup** (boot loop). Same omit-when-blank handling.

> Unlike Render (`generateValue: true` for `JWT_SECRET`), Bicep has no stable
> auto-generate for a persisted secret — `newGuid()` would rotate on every redeploy and log
> everyone out. So `JWT_SECRET` is a **required secure param** you supply and keep.

---

## 4. Generate the secrets

```bash
JWT_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
PG_ADMIN_PASSWORD=$(python -c "import secrets; print(secrets.token_urlsafe(24))")
# Optional:
SECRET_STORE_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
OPS_BOOTSTRAP_TOKEN=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
```

Keep these out of shell history / logs where possible (a `.env`-style file you do **not**
commit, or a keyboard-interactive prompt). They are passed as `@secure()` params, so they
do **not** appear in deployment outputs or the activity log.

---

## 5. Deploy the Bicep

```bash
az deployment group create \
  -g "$RG" \
  -n neuropathy-azure \
  -f infra/azure/main.bicep \
  -p namePrefix=neuropathy \
     location="$LOC" \
     backendImage="$ACR_SERVER/neuropathy-backend:$TAG" \
     frontendImage="$ACR_SERVER/neuropathy-frontend:$TAG" \
     registryServer="$ACR_SERVER" \
     registryUsername="$ACR_USER" \
     registryPassword="$ACR_PASS" \
     postgresAdminLogin=neuro \
     postgresAdminPassword="$PG_ADMIN_PASSWORD" \
     databaseName=neuropathy \
     jwtSecret="$JWT_SECRET" \
     secretStoreKey="$SECRET_STORE_KEY" \
     opsBootstrapToken="$OPS_BOOTSTRAP_TOKEN" \
     webConcurrency=2
```

- Omit `secretStoreKey` / `opsBootstrapToken` to leave them unset (recommended for a first
  bring-up).
- Omit the three `registry*` params if your images are on a public registry.
- Validate first without deploying: replace `create` with `what-if` (`az deployment group
  what-if ...`).

The deployment prints outputs: `frontendUrl`, `backendInternalFqdn`, `postgresFqdn`,
`migrateJobName`, `databaseUrlWasBuilt`.

### 5.1 The `DATABASE_URL` async + SSL form (the one manual wire — automated here)

The app's engine and Alembic require the **async driver scheme** `postgresql+asyncpg://`
(`backend/app/db/session.py`, `backend/alembic/env.py`). Two Azure-specific facts drive the
exact string:

1. **Async scheme, not bare `postgresql://`** — same as Render (the app is intentionally not
   modified to rewrite the scheme).
2. **SSL uses `?ssl=require`, NOT libpq's `?sslmode=require`.** Azure Postgres Flexible
   Server **enforces TLS**, so SSL is mandatory (Render's *internal* URL needed none).
   SQLAlchemy's asyncpg dialect passes URL query params **straight to `asyncpg.connect()`**
   (`create_connect_args` does `opts.update(url.query)`), and `asyncpg.connect()` has an
   `ssl` keyword but **no** `sslmode` keyword. `asyncpg`'s `SSLMode.parse()` accepts
   `require`, `prefer`, `verify-ca`, `verify-full`, etc. So the app wants:

   ```
   postgresql+asyncpg://USER:PASS@HOST.postgres.database.azure.com:5432/DB?ssl=require
   ```

   Passing `?sslmode=require` would make SQLAlchemy call `asyncpg.connect(sslmode='require')`
   → `TypeError: unexpected keyword argument 'sslmode'`. (Verified against the installed
   `sqlalchemy` 2.0 asyncpg dialect and `asyncpg` 0.31 source.)

The template **builds this string for you** from the provisioned server (login, password,
FQDN, db name) into the `database-url` Container Apps secret — you normally do nothing.
`databaseUrlWasBuilt=true` in the outputs confirms it. Only if you pass `databaseUrlOverride`
must you write the string yourself, in exactly the form above.

> **Hardening:** `ssl=require` encrypts but does not verify the server certificate/hostname.
> For cert verification use `?ssl=verify-full`, but that requires the Azure Postgres CA to be
> in the container's trust store and the hostname to match — validate before switching, or it
> will refuse to connect. `require` is the safe baseline against an enforced-TLS server.

---

## 6. Run migrations (before the backend serves new schema)

The migration **Container Apps Job** (`<namePrefix>-migrate`) runs `alembic upgrade head` on
the **same backend image**, with the same `DATABASE_URL` secret. It is **manual-trigger** —
start it explicitly, and wait for it to complete, **before** the backend serves a version
that expects the new schema:

```bash
JOB=$(az deployment group show -g "$RG" -n neuropathy-azure \
        --query properties.outputs.migrateJobName.value -o tsv)

az containerapp job start -n "$JOB" -g "$RG"

# Watch executions until Succeeded:
az containerapp job execution list -n "$JOB" -g "$RG" -o table
# Logs for a specific execution:
az containerapp job logs show -n "$JOB" -g "$RG" --execution <execution-name> --container migrate
```

Why a separate job (matches ADR-0018 / the Render release phase):

- The app **never** self-migrates; `docker-entrypoint.sh` only resets the Prometheus dir
  then `exec "$@"`. The job overrides the image CMD (`gunicorn`) with `alembic upgrade head`
  through the **same entrypoint** — so migrations run in exactly one place, **no double-run**.
- The image WORKDIR is `/app` (holds `alembic.ini` + `alembic/`) and the venv is on `PATH`,
  so `alembic` resolves and reads `DATABASE_URL` from app settings (`alembic/env.py`).

Ordering: on a fresh stack, `az deployment group create` provisions everything, then you run
the job once. On subsequent app upgrades, run the migration job **before** rolling the
backend to the new image if the release includes a migration.

---

## 7. How the frontend points at the backend (same-origin reverse-proxy)

The Bicep wires the SPA to the API the same way `render.yaml` does:

- `API_BASE_URL=""` (same-origin) and
- `BACKEND_ORIGIN` = the backend app's **internal FQDN** (`backendInternalFqdn` output).

nginx (`frontend/nginx.conf.template`) reverse-proxies `/auth`, `/observations`,
`/trajectory`, `/emr/*`, `/clinic/*`, `/ops/*`, … to `BACKEND_ORIGIN` over the environment's
internal network, so the browser only ever talks to one origin and **no backend CORS layer
is needed** (the backend ships none). Internal ingress serves plain HTTP on port 80, which
nginx's `proxy_pass http://$backend_origin` targets by default.

### 7.1 KNOWN CAVEAT — the nginx Docker resolver (open decision, needs a decision before prod)

`frontend/nginx.conf.template` hardcodes **`resolver 127.0.0.11`** — Docker's embedded DNS —
because it uses a *variable* in `proxy_pass` (which forces per-request DNS resolution). **That
address does not exist in Azure Container Apps** (the platform is Kubernetes-based; DNS is the
cluster resolver, not `127.0.0.11`). As delivered, the frontend's variable `proxy_pass` will
therefore fail to resolve `BACKEND_ORIGIN` in Container Apps (typically a 502 on API paths;
the SPA shell still loads). A secondary issue: the template sets `Host $host`, but Container
Apps internal ingress routes by the **target FQDN** in the Host header.

This infra work **does not modify frontend/backend application logic** (out of scope), so this
is flagged as an **open decision**. Options, in order of preference:

1. **Small frontend follow-up (recommended):** make the nginx `resolver` (and the proxied
   `Host`) environment-driven — substitute the platform DNS at container start via the
   existing `envsubst` entrypoint, and set `Host` to `$backend_origin`. One-line-ish change,
   keeps the same-origin/no-CORS design intact on Azure. Owned by the frontend, tracked
   separately.
2. **Verify per-environment:** if a given Container Apps environment happens to expose a
   compatible resolver, confirm end-to-end (§9) before relying on it. Do not assume.
3. **Cross-origin (not recommended):** point the frontend `API_BASE_URL` at the backend's
   public URL and give the backend an **external** ingress — but the backend has **no CORS
   layer**, so browser calls are blocked until CORS is added to the backend. This trades the
   resolver problem for a CORS problem; prefer option 1.

Until option 1 lands, treat the Azure frontend reverse-proxy as **not yet verified for
production**; the backend itself (auth, check-ins, migrations, health) is fully functional and
directly testable from inside the environment.

---

## 8. AI layer → Azure OpenAI (wiring point only — not implemented here)

The narrative layer (ADR-0011) is **gated OFF by default** and stays off until a covered
entity both supplies a provider key **and** sets the explicit BAA attestation
(`AI_BAA_CONFIRMED`) — the LLM is never in the request path, and it sends only the computed
Trajectory, never raw PHI (`docs/compliance/baa-inventory.md`).

On Azure the natural provider is **Azure OpenAI**, which is **covered by your Microsoft BAA**
(no separate Anthropic BAA needed for that path). The wiring point is config only
(`backend/app/core/config.py`): `AI_PROVIDER`, `AI_API_KEY`, `AI_MODEL`, and the
`AI_BAA_CONFIRMED=true` attestation, provided as additional Container App secrets/env on the
backend. **Do not enable it as part of this deploy** — and note that `api/deps.py` currently
selects the narrator on an `anthropic` provider check, so pointing at Azure OpenAI is a
**separate application change** (a provider adapter), not a config-only swap. This runbook only
records where the switch lives; the model swap is out of scope.

---

## 9. Verify it's live (checklist)

Backend (internal) is reachable from inside the environment; the frontend is public. Two
angles:

**A. Backend directly** (exec into a running container, or a temporary debug container in the
same environment) — proves the API + DB independent of the frontend proxy caveat (§7.1):

```bash
# Health (liveness + readiness). readyz "mode":"database" confirms DATABASE_URL is wired.
curl -fsS http://<backendInternalFqdn>/healthz   # {"status":"ok"}
curl -fsS http://<backendInternalFqdn>/readyz    # {"status":"ready","mode":"database"} (200; 503 if DB down)

# Register + login (durable auth end-to-end):
curl -fsS -X POST http://<backendInternalFqdn>/auth/register -H 'content-type: application/json' \
  -d '{"email":"you@example.com","password":"a-strong-passphrase"}'
curl -fsS -X POST http://<backendInternalFqdn>/auth/login -H 'content-type: application/json' \
  -d '{"email":"you@example.com","password":"a-strong-passphrase"}'   # -> access token

# Submit a check-in with the bearer token (e.g. POST /observations), then restart the backend
# and re-read — persistence across restart proves durable Postgres mode, not the in-memory store.
```

(Confirm exact request bodies against `backend/app/api/routes/` if they differ.)

**B. Through the frontend** (`frontendUrl`): load the SPA, open `/config.js` (should set
`apiBaseUrl` to `""`), and complete register → login → check-in in the UI. If API calls 502 /
fail, that is the §7.1 resolver caveat — verify via angle A that the backend is healthy, then
resolve §7.1.

---

## 10. Notes, secrets, and open decisions

- **No secrets in git.** Every credential is a `@secure()` param or a value built into a
  Container Apps secret at deploy time; none appears in template outputs or the activity log.
  The `.env.example` files hold placeholders only.
- **Async DB driver + SSL** — the one "manual" wire, automated by the template (§5.1):
  `postgresql+asyncpg://…?ssl=require` (asyncpg's `ssl`, not libpq's `sslmode`).
- **Frontend reverse-proxy on Container Apps** — the nginx Docker-resolver caveat (§7.1) is
  the top open item; decide before production.
- **Database networking** — the template uses **public access + an "allow Azure services"
  firewall rule** for simplicity. For a hardened PHI posture, switch Flexible Server to
  **private access** (VNet integration + Private DNS) and place the Container Apps environment
  on the same VNet; parameterize accordingly. Open decision.
- **Region / SKU** — defaults: `location = resourceGroup().location`, Postgres
  `Standard_B1ms` / Burstable / 32 GB, small container CPU/memory. Right-size and pick a
  region in your BAA scope. Burstable Postgres is fine to start; move to GeneralPurpose for
  real load. Open decision.
- **TLS / custom domain** — Container Apps terminates TLS automatically for its generated
  `*.azurecontainerapps.io` FQDNs. For a custom domain, bind it + a managed certificate on the
  **frontend** app (`az containerapp hostname add` / `... bind`). Open decision.
- **Backups** — Flexible Server backup retention is set to 7 days (geo-redundant disabled).
  Adjust for your RPO; back up `SECRET_STORE_KEY` **separately** from the DB
  (`docs/ops/backup-restore.md`).
- **Log Analytics** — app logs are engineered PHI-free (ADR-0018 §4), but the workspace is in
  BAA scope; confirm Azure Monitor is covered (§0).
