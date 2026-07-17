# Deploy runbook — running the real app (login + use), not the static mock

This is the step-by-step guide to stand up a **real, running** neuropathy-app: the
FastAPI backend + a managed Postgres database, with the SPA pointed at it so users can
register, log in, and submit check-ins. It is written for **Render** (a Docker web
service + managed Postgres, via `render.yaml`) but the container contract is
vendor-neutral — a matching "any Docker host" section follows so you are not locked in.

Companion docs: `docs/ops/deployment.md` (host-agnostic image contract, full env table),
`docs/ops/backup-restore.md`, `docs/ops/observability.md`. Architecture decisions:
ADR-0018 (topology), ADR-0010/0017 (secrets), ADR-0021 (server/metrics).

> **Provisioning needs your own account + billing.** Nothing here creates cloud
> resources on its own, and **no secrets are committed** — every credential is generated
> or entered at deploy time. You need a Render (or other host) account, and a paid
> instance/DB tier for anything durable (see notes inline).

---

## 1. What gets deployed (architecture)

There are two distinct things people call "the app":

| | The **mock demo** (static) | The **real app** (this runbook) |
|---|---|---|
| What it is | Prebuilt SPA / mockups, no backend | SPA + FastAPI API + Postgres |
| Auth / data | None — canned UI | Real register/login (JWT), durable check-ins |
| Where | Any static host / `mockups/` | Backend container + managed Postgres |

The real app is three pieces:

```
  browser ──HTTPS──> frontend (nginx, serves SPA)
                        │  reverse-proxies /auth, /observations, /trajectory, ... (same-origin)
                        ▼
                     backend (Gunicorn + Uvicorn, app.main:app)  ──async──>  Postgres
```

- **Backend** — `backend/Dockerfile`, runs `gunicorn app.main:app --config
  gunicorn.conf.py`, binds `0.0.0.0:$PORT` (Render injects `PORT`; the config honors it).
  Health: `GET /healthz` (liveness, always fast) and `GET /readyz` (readiness — runs a
  bounded `SELECT 1` in DB mode).
- **Database** — managed Postgres. The app runs in **durable mode** only when
  `DATABASE_URL` is set; unset means non-durable in-memory stores (dev/test only).
- **Frontend** — `frontend/Dockerfile`, non-root nginx. One immutable image; the API
  base URL is injected at container start into `/config.js`
  (`window.__APP_CONFIG__.apiBaseUrl`, see `frontend/src/api/runtimeConfig.ts`).
  Because the **backend ships no CORS layer** (by design), the frontend nginx
  **reverse-proxies the API to the backend**, so the browser only ever talks to one
  origin. `API_BASE_URL=""` (same-origin) + `BACKEND_ORIGIN=<backend host:port>`.

### Migrations (schema is applied *before* the app serves)

The app **never migrates its own schema** (files-only rule, `backend/README.md`;
`app/main.py` lifespan builds the engine but creates no tables). Migrations are a
separate one-shot: **`alembic upgrade head`**, run from the image's WORKDIR `/app`
(where `alembic.ini` and `alembic/` live; the venv is on `PATH`). It reads `DATABASE_URL`
from app settings (`alembic/env.py`). The container entrypoint does **not** migrate on
boot (`backend/docker-entrypoint.sh` only resets the Prometheus dir, then `exec "$@"`),
so putting migrations in Render's release phase means **no double-run**.

---

## 2. Deploy on Render (Blueprint)

### 2.1 Prerequisites
- A Render account with billing enabled (the Blueprint requests `starter` services + a
  Postgres DB). `preDeployCommand` (release-phase migrations) requires a **paid** instance
  type.
- This repo pushed to a Git host Render can connect to.

### 2.2 Connect the repo as a Blueprint
1. Render Dashboard → **New** → **Blueprint**.
2. Select this repository. Render reads **`render.yaml`** at the repo root and shows a
   plan: `neuropathy-backend` (web), `neuropathy-frontend` (web), `neuropathy-db`
   (Postgres).
3. Render will prompt for every `sync: false` env var before it can deploy (next step).

### 2.3 Set the secrets Render prompts for

| Env var | Who sets it | How |
|---|---|---|
| `DATABASE_URL` | **You (required)** | See 2.4 — it needs a scheme rewrite, so it is manual. |
| `SECRET_STORE_KEY` | You (optional*) | Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `OPS_BOOTSTRAP_TOKEN` | You (optional**) | `python -c "import secrets; print(secrets.token_urlsafe(48))"` (≥32 chars) |

Auto-generated / auto-set (you do **nothing**):

| Env var | Source |
|---|---|
| `JWT_SECRET` | `generateValue: true` — Render generates a strong secret. |
| `APP_ENV`, `APP_DEBUG`, `WEB_CONCURRENCY` | Fixed values in `render.yaml`. |
| `PORT` | Injected by Render; honored by `gunicorn.conf.py`. |
| `BACKEND_ORIGIN` (frontend) | `fromService` → backend's internal `host:port`. |

\* `SECRET_STORE_KEY` — leave blank for basic register/login/check-in. It only encrypts
the DB-backed **EMR OAuth token vault**; without it those tokens stay in a per-process
in-memory vault (fail closed — never written to the DB in plaintext). Required only for
durable EMR connections. **If you set it, back it up separately from the database**
(`docs/ops/backup-restore.md`) — losing it makes stored EMR tokens undecryptable.

\*\* `OPS_BOOTSTRAP_TOKEN` — leave blank unless you need to provision **clinician**
accounts. Blank disables provisioning (patient register/login is unaffected). If set it
must be ≥32 chars or the backend **fails closed at startup** (boot loop).

> `JWT_SECRET` is auto-generated. If you ever need tokens to stay valid across an
> environment rebuild, switch it to `sync: false` and set it yourself instead — otherwise
> a regenerated value logs everyone out.

### 2.4 The one manual wire: `DATABASE_URL` (async driver)

The app's engine and Alembic use the **async** driver and require the
`postgresql+asyncpg://` scheme. Render's managed-Postgres connection string uses the bare
`postgresql://` scheme, and the app is intentionally **not** modified to rewrite it. So:

1. After the Blueprint provisions `neuropathy-db`, open it in the dashboard and copy its
   **Internal Database URL** (looks like `postgresql://neuro:PASS@HOST/neuropathy`).
   Use the **internal** URL — it needs no SSL param, which suits asyncpg (asyncpg does
   not accept libpq's `?sslmode=`).
2. Rewrite the scheme prefix `postgresql://` → **`postgresql+asyncpg://`**. If any
   `?sslmode=...` / `?ssl=...` query is present, drop it.
3. Paste the result into the backend's `DATABASE_URL` (the `sync: false` value Render
   prompts for).

   ```
   postgresql://neuro:PASS@dpg-xxxx/neuropathy
   ->  postgresql+asyncpg://neuro:PASS@dpg-xxxx/neuropathy
   ```

> `render.yaml` shows the `fromDatabase` auto-wire commented out with the reason: it would
> inject the wrong (non-asyncpg) scheme. Doing this one field by hand is the tradeoff for
> not modifying app code.

### 2.5 Deploy

Apply the Blueprint. Order of operations per deploy:
1. Build the backend image.
2. **Release phase** runs `alembic upgrade head` against `DATABASE_URL` (migrates the
   schema *before* the new version serves).
3. The new backend goes live once `GET /healthz` returns 200.
4. The frontend builds and starts; its nginx proxies the API to `BACKEND_ORIGIN`.

### 2.6 Point the frontend at the API (already wired, how it works)

The Blueprint wires the SPA to the API for you via **same-origin reverse-proxy**:
`API_BASE_URL=""` and `BACKEND_ORIGIN` = the backend's internal `host:port`
(`fromService`). nginx proxies the API paths to the backend, so the browser uses one
origin and no CORS is involved.

- **If internal `hostport` doesn't resolve** in your Render setup: set the frontend's
  `BACKEND_ORIGIN` to the backend's internal address manually.
- **Alternative (cross-origin), not recommended:** set the frontend's `API_BASE_URL` to
  the backend's public URL (e.g. `https://neuropathy-backend.onrender.com`). This writes
  `window.__APP_CONFIG__.apiBaseUrl` to that URL and adds it to the CSP `connect-src`
  — **but the backend has no CORS layer**, so browser calls will be blocked until a CORS
  middleware/allowed-origins config is added to the backend. Prefer the reverse-proxy.

---

## 3. Any Docker host (Fly.io / Railway / a plain VM)

Same two images, same env, same release step — nothing here is Render-specific.

1. **Provision Postgres** (managed or a `postgres:16` container). Get a connection URL and
   express it as `postgresql+asyncpg://USER:PASS@HOST:5432/DB`.
2. **Build/push images** (or build on the host):
   ```bash
   docker build -t neuropathy-backend:<tag> ./backend
   docker build -t neuropathy-frontend:<tag> ./frontend
   ```
3. **Run migrations once, before starting the server** — same image, override the CMD:
   ```bash
   docker run --rm -e DATABASE_URL="postgresql+asyncpg://USER:PASS@HOST:5432/DB" \
     neuropathy-backend:<tag> alembic upgrade head
   ```
   (The entrypoint execs the override; WORKDIR `/app` already holds `alembic.ini`.)
4. **Run the backend** with the required env:
   - `DATABASE_URL` (async scheme, as above) — required for durable mode.
   - `JWT_SECRET` — required for durable auth (`token_urlsafe(48)`).
   - `SECRET_STORE_KEY` — Fernet key; only if storing EMR tokens.
   - `OPS_BOOTSTRAP_TOKEN` — only to provision clinicians (≥32 chars).
   - `APP_ENV=production`, `APP_DEBUG=false`, `WEB_CONCURRENCY=<cpu>`.
   - Bind port: the server uses `$PORT` (default 8000). Expose/publish it.
   ```bash
   docker run -d -p 8000:8000 --env-file backend.env neuropathy-backend:<tag>
   ```
5. **Run the frontend** with `API_BASE_URL=""` and `BACKEND_ORIGIN=<backend host:port>`
   for same-origin reverse-proxy (no CORS), publishing container port 8080. Put TLS in
   front (a load balancer / the host's HTTPS). The compose file `docker-compose.yml` is a
   working reference for this wiring (it is a **staging** topology, not hardened prod).

Platform mapping: Fly.io → `fly.toml` with a `[deploy] release_command = "alembic
upgrade head"`; Railway → a pre-deploy/release command with the same string. The contract
is identical: one image, the env vars above, `alembic upgrade head` before serving.

> **Azure** — for a first-class Azure path (Container Apps + Azure Database for PostgreSQL
> Flexible Server) as Infrastructure-as-Code, see the Bicep template `infra/azure/main.bicep`
> and the dedicated runbook **[`docs/ops/deploy-azure.md`](./deploy-azure.md)**. It follows
> the same contract (one image each, the env vars above, `alembic upgrade head` in a
> Container Apps **Job** before serving) and documents the Azure-specific
> `DATABASE_URL` form: `postgresql+asyncpg://…?ssl=require` (asyncpg's `ssl`, not libpq's
> `sslmode`, because Azure Postgres enforces TLS). **PHI note:** a signed Microsoft BAA is
> required before real PHI — called out prominently in that runbook.

---

## 4. Verify it's live (checklist)

Replace `$API` with the backend origin (its public URL, or the frontend origin since it
proxies the API same-origin).

1. **Health**
   ```bash
   curl -fsS $API/healthz     # {"status":"ok"}
   curl -fsS $API/readyz      # {"status":"ready","mode":"database"}  (200; 503 if DB down)
   ```
   `mode":"database"` confirms `DATABASE_URL` is wired (in-memory mode would say
   `"in-memory"`).
2. **Register + login** (durable auth end-to-end):
   ```bash
   curl -fsS -X POST $API/auth/register -H 'content-type: application/json' \
     -d '{"email":"you@example.com","password":"a-strong-passphrase"}'
   curl -fsS -X POST $API/auth/login -H 'content-type: application/json' \
     -d '{"email":"you@example.com","password":"a-strong-passphrase"}'   # -> access token
   ```
   (Confirm the exact request bodies against `backend/app/api/routes/` if they differ.)
3. **Submit a check-in** with the bearer token from login (e.g. `POST /observations` or
   the ADL/labs route your build exposes) and confirm it persists across a backend
   restart — that proves durable Postgres mode, not the in-memory store.
4. **Frontend**: load the SPA URL, open `/config.js` (should set `apiBaseUrl`), and
   complete register→login→check-in through the UI.

---

## 5. Notes, secrets, and open decisions

- **No secrets in git.** `JWT_SECRET` is generated by the platform; `DATABASE_URL`,
  `SECRET_STORE_KEY`, `OPS_BOOTSTRAP_TOKEN` are entered at deploy time. The `.env.example`
  files hold placeholders only.
- **Async DB driver** — the one manual step (§2.4); flagged for your awareness.
- **CORS** — the backend has no CORS layer; the reverse-proxy design sidesteps it. A
  cross-origin frontend would require adding CORS to the backend first.
- **Region / plan** — `render.yaml` uses `oregon` + `starter`/`free`; change to your
  region and right-size the plans. Same-region is required for the `fromService`
  internal-network wire and managed-DB proximity.
- **Custom domain / TLS** — add via the host's dashboard; Render terminates TLS
  automatically for its `*.onrender.com` URLs and custom domains.
- **Backups** — the `free` Postgres plan has none and is deleted ~30 days after creation;
  upgrade before real use and see `docs/ops/backup-restore.md` (back up `SECRET_STORE_KEY`
  separately from the DB).
