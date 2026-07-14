# Deployment (host-agnostic)

How to build, configure, migrate, run, health-check, and roll back the neuropathy app.
Decisions and rationale: **ADR-0018**. This describes the container images and their
contract; it is not tied to a specific orchestrator. The bundled `docker-compose.yml`
is a **staging/dev** topology (ADR-0018 staging boundary), not a hardened production
deployment.

## Images

Two images, both multi-stage, non-root, secret-free:

| Image | Build context | Serves | Port |
|---|---|---|---|
| backend | `backend/` | FastAPI via uvicorn (`app.main:app`) | 8000 |
| frontend | `frontend/` | Built SPA via non-root nginx (reverse-proxies the API) | 8080 |

```bash
docker build -t neuropathy-backend:<tag> ./backend
docker build -t neuropathy-frontend:<tag> ./frontend
```

Neither image bakes in a secret. All backend config is read from the environment at
runtime (`backend/app/core/config.py`); the frontend API base URL is injected at
container start (`/config.js`, see "Frontend runtime config" below).

## Configuration (environment)

The backend's full env surface is defined in `backend/app/core/config.py`. Values marked
**SECRET** must come from a secret manager (or a gitignored `.env` for staging), never
the repo. Security-sensitive values **fail closed at startup** with an actionable error
(ADR-0017) rather than booting into a weaker posture.

| Variable | Secret? | Required | Purpose / how to generate |
|---|---|---|---|
| `DATABASE_URL` | secret (embeds DB password) | for durable mode | `postgresql+asyncpg://USER:PASSWORD@HOST:5432/DB`. Unset = in-memory (non-durable; dev/test only). |
| `APP_ENV` | no | no | Environment label (e.g. `staging`, `production`); appears in logs. |
| `APP_DEBUG` | no | no | `true` raises log verbosity and enables SQL echo. Keep `false` in prod. |
| `WEB_CONCURRENCY` | no | no | uvicorn worker count (default 2). Size by CPU. |
| `JWT_SECRET` | **SECRET** | yes for durable auth | Signs JWT access/refresh tokens (ADR-0010). Without it, tokens don't survive restarts/multiple workers. `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `SECRET_STORE_KEY` | **SECRET** | if storing EMR tokens | Fernet key encrypting the DB OAuth token vault (ADR-0017). Fail-closed: without it, tokens stay in a per-process in-memory vault (never written to the DB in plaintext). **Back this up separately from the database** (see backup-restore.md). `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `OPS_BOOTSTRAP_TOKEN` | **SECRET** | to provision clinicians | Ops gate for clinician provisioning (ADR-0012/0017). Min 32 chars — shorter is refused at startup. Unset = provisioning disabled (fails closed). `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `SMART_CLIENT_ID` / `SMART_REDIRECT_URI` | client id no / secret lives in the vault | for EMR pull | SMART on FHIR config (ADR-0008/0009). |
| `AI_API_KEY` + `AI_BAA_CONFIRMED` | **SECRET** (key) | for AI narrative | The narrative layer stays OFF without both a key AND the explicit BAA attestation (ADR-0011). |

Frontend (set at container start):

| Variable | Secret? | Purpose |
|---|---|---|
| `API_BASE_URL` | no (public URL) | The API origin the browser calls. Empty = same-origin (nginx reverse-proxies to the backend). A cross-origin value is also appended to the CSP `connect-src`. |
| `BACKEND_ORIGIN` | no | `host:port` of the backend for nginx's reverse proxy (default `backend:8000`). |

## Frontend runtime config (no rebuild per environment)

Vite inlines `import.meta.env.*` at **build** time, so the API base URL cannot be baked
into a reusable image. Instead the frontend entrypoint writes `/config.js` at **start**
time from `API_BASE_URL`, and `index.html` loads it before the app bundle
(`window.__APP_CONFIG__.apiBaseUrl`, resolved in `src/api/runtimeConfig.ts`). One
immutable image therefore serves every environment — dev, staging, prod — by changing
only an env var. `/config.js` is served `no-cache` so a redeploy takes effect
immediately.

## Migrations (files-only, before boot)

Schema is owned by Alembic and applied by an explicit step **before** the app boots — the
app never migrates itself (`backend/README.md`, files-only rule). The backend image
contains the migration files, so run migrations with the **same image**:

```bash
docker run --rm -e DATABASE_URL="postgresql+asyncpg://USER:PASSWORD@HOST:5432/DB" \
  neuropathy-backend:<tag> alembic upgrade head
```

In compose this is the one-shot `migrate` service; `backend` waits for it via
`depends_on: { migrate: { condition: service_completed_successfully } }`.

## Bring up (staging compose)

```bash
cp .env.example .env        # fill in secrets; .env is gitignored
docker compose up --build   # db (healthcheck) -> migrate -> backend -> frontend
```

The SPA is published on `http://localhost:${FRONTEND_PORT}` (default 8080).

## Health checks

- **Backend liveness** — `GET /healthz` → `200 {"status":"ok"}`. No dependencies; used
  by the image `HEALTHCHECK` and by orchestrator liveness probes to restart a hung
  process.
- **Backend readiness** — `GET /readyz` → `200` when ready; `503` (PHI-free body) when
  the database is unreachable. Use for load-balancer rotation / readiness probes so an
  instance that can't reach its DB is pulled without being killed.
- **Frontend liveness** — `GET /healthz` on the frontend serves nginx's own `200`.

```bash
curl -fsS http://BACKEND:8000/healthz
curl -fsS http://BACKEND:8000/readyz
```

## Roll back

Images are immutable and tagged, and migrations are decoupled from boot, so a rollback
is a redeploy of the previous tag:

1. Redeploy the previous **backend**/**frontend** image tags.
2. Migrations are **forward-only** in this repo. If the previous release predates the
   current schema, prefer a forward fix-migration; only restore the database (see
   backup-restore.md) if a schema rollback is truly required, and remember that a
   restored DB needs its matching `SECRET_STORE_KEY` to decrypt vaulted tokens.
3. Re-run `GET /readyz` on the rolled-back instances before returning them to rotation.

## Not covered here (production hardening)

TLS termination, a real API gateway, managed/replicated Postgres, secret rotation,
centralized logging/metrics/alerting, and autoscaling are production concerns owned by
the ops/observability portions — deliberately out of scope for this staging topology
(ADR-0018).
