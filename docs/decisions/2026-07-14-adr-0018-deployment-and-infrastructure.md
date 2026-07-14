# ADR-0018: Deployment & Infrastructure — Containers, Health/Readiness, PHI-Free Logging, Staging Topology

**Date:** 2026-07-14
**Status:** Accepted
**Builds on:** ADR-0004 (backend stack; files-only migrations), ADR-0010 (JWT secret),
ADR-0015 (patient UI / Vite build), ADR-0017 (fail-closed config, encrypted token
vault, blocking scans).

## Context

The app was runnable locally (uvicorn `--reload`, `vite`) but had no deployable
artifacts: no container images, no health/readiness contract for an orchestrator, no
structured logs, no staging topology, and no deploy/backup runbooks. This portion adds
that infrastructure for the first packaged deployment, under the health-data posture
(no secrets in images, no PHI in logs).

## Decision

### 1. Container strategy — multi-stage, non-root, secret-free

Both images are multi-stage and run as a dedicated **non-root** user:

- **Backend** (`backend/Dockerfile`, `python:3.12-slim`): a builder installs the package
  into an isolated venv; the final stage copies **only** that venv plus the alembic
  migration files — no build toolchain, no caches, no tests. The **same image** runs the
  app (`uvicorn app.main:app`, no `--reload`, workers from `WEB_CONCURRENCY`, bound
  `0.0.0.0:8000`) or the migrations (`alembic upgrade head`). `HEALTHCHECK` hits
  `/healthz` via stdlib urllib (no curl added to the image).
- **Frontend** (`frontend/Dockerfile`, `node:22` build → `nginx:alpine`): the SPA is
  served by a fully non-root nginx (pid + temp paths under `/tmp`, listens on 8080),
  with SPA history-API fallback, gzip + long-cache for hashed assets, `no-cache` for the
  app shell and runtime config, and security headers (CSP, `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, COOP).

**No secret is ever baked into an image.** Backend config is read from the environment at
runtime (`app/core/config.py`); the frontend carries no secret at all. Bases are pinned
by tag with a comment to also pin by digest in production. `.dockerignore` files keep
`.env`, tests, caches, and `node_modules` out of the build context.

### 2. Frontend runtime config — not build-time — for the API base URL

Vite inlines `import.meta.env.*` at **build** time, so an image with the API URL baked
in could not be reused across environments. Instead the container entrypoint writes
`/config.js` at **start** time from `API_BASE_URL`
(`window.__APP_CONFIG__.apiBaseUrl`), and `index.html` loads it before the bundle;
`src/api/runtimeConfig.ts` resolves runtime → build-time env → same-origin, so one
immutable image serves any environment by changing only an env var. `/config.js` is
served `no-cache`. Because the backend has no CORS layer, the default deployment is
**same-origin**: the frontend nginx reverse-proxies the API to the backend. A
cross-origin `API_BASE_URL` is also appended to the CSP `connect-src` at start time.

The `/clinic` namespace is **both** an SPA route (`/clinic`, `/clinic/patients/{id}`)
and an API namespace (`/clinic/patients`, `/clinic/patients/{id}/trajectory`, …). The
nginx config proxies only the exact and id-with-suffix API routes; the bare SPA routes
fall through to the history fallback. This coupling of the proxy to API route shapes is
acceptable for staging; a production gateway would front the API on its own origin
(where the runtime-config feature earns its keep).

### 3. Health vs readiness — distinct semantics

- `GET /healthz` — **liveness**: process is up. Checks no dependency, never touches the
  DB, always fast `200`. An orchestrator uses it to restart a hung process without being
  fooled by a slow-but-alive database.
- `GET /readyz` — **readiness**: ready to serve traffic *now*. In DB mode it opens a
  connection and runs `SELECT 1` with the **whole probe** — the TCP connect + Postgres
  handshake *and* the query — bounded by a short (2s) timeout, so a network-partitioned
  DB (which stalls at the handshake, outside a query-only timeout) still fails fast
  instead of holding a pool checkout for asyncpg's 60s default. The engine additionally
  caps connection *establishment* at 5s (`connect_args={"timeout": 5}`, app/db/session.py)
  so establishment is bounded everywhere, not only under the probe. In-memory mode reports
  ready with no dependency. Not ready → **503** with a fixed, PHI-free body, so a load
  balancer pulls the instance from rotation without killing it.

Neither endpoint exposes secrets, leaky version/build detail, or PHI — the bodies are
fixed status dicts. The underlying DB error on `/readyz` is deliberately **not** echoed
(it can carry host/DSN detail). The existing `/` service dict is unchanged.

### 4. Structured, PHI-free request logging

`app/core/logging.py` adds a `RequestLoggingMiddleware` that emits **one JSON line per
request** on stdout (Twelve-Factor). It is **registered last** in `create_app`, which is
what makes it genuinely outermost — Starlette wraps the last-added middleware around all
earlier ones, so it times the whole request *and* still logs (with an `X-Request-ID`)
responses short-circuited by the inner upload guard, which an "added first" registration
would have skipped. The line carries a **whitelist** only: `method`, `path`, `status`,
`duration_ms`, `request_id`, `env`. Rules that make it PHI-free:

- **`path` is the matched route *template*** (`/clinic/patients/{id}`), read from
  `request.scope["route"]` after routing — never the raw path, which can embed a patient
  id, an email, or a token in a segment. An unmatched request logs `__unmatched__`, not
  its raw path.
- **Never logged:** query strings, request/response bodies, headers
  (`Authorization`/cookies/tokens), path-parameter *values*, or anything derived from
  them. There is no code path that widens the set — the dict is built from the whitelist,
  and `tests/test_logging.py` asserts the exact field set and that a synthetic id/email
  in the URL never reaches the line. Any widening breaks a test.
- `request_id` comes from an inbound `X-Request-ID` or is generated, and is echoed on
  the response for trace correlation. Level follows `app_debug`.
- **The nginx layer is PHI-free too.** nginx's built-in `combined` access-log format logs
  the raw request line (`$request`) and query string, which would leak patient UUIDs
  (`/clinic/patients/<uuid>/...`) and the single-use OAuth `code`+`state`
  (`/emr/callback?...`) into captured stdout — re-introducing exactly what the backend
  whitelist excludes. `nginx.conf.template` therefore defines a `phi_free` `log_format`
  that logs **only** `$request_method`, `$status`, `$request_time`, `$upstream_status`,
  and `$http_x_request_id` (so a line correlates with the backend's request id) — no
  `$request`, `$request_uri`, `$query_string`, or `$uri`. `error_log` is set to `error`
  (not `warn`) so routine chatter is dropped; nginx still appends the request line to a
  message on a *hard* upstream error, the one unavoidable place a raw path can surface,
  but at `error` level for these proxy paths that message carries no query string.
  `tests/test_nginx_logging.py` asserts the access-log format contains none of the
  path/query variables.

### 5. Staging compose topology (explicitly not production)

`docker-compose.yml` wires `postgres:16` (named volume, healthcheck) → one-shot
`migrate` (`alembic upgrade head`, gated on DB health) → `backend` (gated on migrate
completing) → `frontend`. This enforces the **migration-before-boot** rule (the app
never migrates itself). All config is `${VAR}` references resolved from a gitignored
`.env`; only `.env.example` (dev defaults + placeholders) is committed — verified against
`.gitignore` and the secret scan. The compose Postgres password is `${POSTGRES_PASSWORD}`
with a documented dev default in `.env.example`, never a committed literal.

This is a **staging/dev** topology: no TLS, no gateway, no managed/replicated Postgres,
no secret rotation, no centralized observability. Those are production concerns owned by
the ops/observability portions — the staging-vs-production boundary is drawn here on
purpose.

### 6. The `SECRET_STORE_KEY` backup trap

EMR OAuth tokens are encrypted at rest in the DB (ADR-0017); the DB backup holds only
ciphertext. **If the database is backed up but `SECRET_STORE_KEY` is lost, every vaulted
token in that backup is permanently unrecoverable.** `docs/ops/backup-restore.md`
therefore requires backing the key up **separately** from the database (different store,
so one loss/compromise never takes both), treats rotation as a re-encryption migration,
and notes that a restore is only complete with the matching-era key. DB dumps are PHI and
handled as such.

### 7. CI — build both images, keep existing jobs untouched

CI gains a `docker` job that lints both Dockerfiles (hadolint), validates
`docker compose config`, and builds **both** images (`docker build`, no push) so image
breakage is caught on every PR. Building on the GitHub runner has real network to
registries (unlike the authored-here sandbox, whose TLS-intercepting egress proxy blocks
in-container package installs — see Consequences). The existing `backend`, `frontend`,
and `security` jobs are unchanged.

## Consequences

- New deployable artifacts: `backend/Dockerfile` (+ `.dockerignore`),
  `frontend/Dockerfile` (+ `.dockerignore`, `nginx.conf.template`,
  `docker-entrypoint.sh`, `public/config.js`), root `docker-compose.yml` + `.env.example`,
  `docs/ops/deployment.md`, `docs/ops/backup-restore.md`.
- New endpoint `/readyz`; `/healthz` unchanged. Backend coverage stays 100% (unit tests
  cover in-memory-ready, engine-missing, and unreachable-DB paths; the Postgres
  integration suite pins the ready-against-live-DB path).
- New frontend module `src/api/runtimeConfig.ts` (100% covered) and an `index.html`
  `/config.js` shim; `client.ts` resolves the base URL per call. `public/` is excluded
  from ESLint (static assets, browser globals it does not declare).
- **What was executed while authoring:** all backend gates (ruff, mypy --strict, pytest
  at 100% incl. live Postgres) and all frontend gates (tsc, eslint, prettier, vitest,
  vite build) pass. Both Docker images were **built and run** here to validate them
  (non-root confirmed; `/healthz`, `/readyz`, `/config.js` injection, CSP headers, and
  SPA fallback all verified), and `docker compose config` validated — the in-container
  package installs required trusting the sandbox proxy CA, which is a sandbox artifact,
  not part of the committed images; on a normal network the plain Dockerfiles build
  as-is.
- New dependencies: none (all tooling is stdlib/existing; nginx + gettext come from the
  base images).
