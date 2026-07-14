# syntax=docker/dockerfile:1
#
# Backend image (ADR-0018). Multi-stage: a builder installs the package into an
# isolated virtualenv, and the slim final stage copies ONLY that venv plus the alembic
# migration files — no build toolchain, no caches, no source tree beyond what runs.
# The image bakes in NO secrets; all config (DATABASE_URL, JWT_SECRET, SECRET_STORE_KEY,
# OPS_BOOTSTRAP_TOKEN, AI_*) is supplied by the environment at runtime (config.py).

# Base pinned to a specific minor tag. For production, ALSO pin by digest
# (python:3.12-slim@sha256:<digest>) and bump deliberately — a bare tag lets the base
# drift between builds. Left as a tag here so the image builds where the digest is not
# pre-cached.
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build in an isolated venv so only runtime artifacts cross into the final image.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
# Copy the build metadata and package, then install. asyncpg/cryptography ship manylinux
# wheels for slim, so no compiler is needed; if a source build were ever required it
# would live in THIS stage only and never reach the final image.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    # Uvicorn worker count — override per deployment. Sized by CPU in prod.
    WEB_CONCURRENCY=2 \
    # Prometheus multiprocess exposition dir (ADR-0021): with >1 worker, per-worker metric
    # series would otherwise round-robin and corrupt rate()/alerts. Workers write here and a
    # /metrics scrape aggregates all of them; the entrypoint wipes it on a fresh start. On
    # tmpfs-friendly /tmp, owned by the non-root `app` user, and torn down with the container.
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus-multiproc

# Least privilege: a dedicated non-root system user owns and runs the process.
RUN groupadd --system app && useradd --system --gid app --home-dir /app app

# Runtime artifacts only: the venv (with the installed package), the alembic migration files
# (so the SAME image can run the app OR `alembic upgrade head`), and the server entrypoint +
# gunicorn config that wire the multiprocess metrics.
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY gunicorn.conf.py ./gunicorn.conf.py
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh

USER app

EXPOSE 8000

# Liveness probe hits /healthz (no dependencies, always fast). Uses stdlib urllib so no
# extra package (curl/wget) enters the image.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"

# The entrypoint clears PROMETHEUS_MULTIPROC_DIR on a fresh start, then execs the CMD (or an
# override like `alembic upgrade head` — the migration one-shot uses the same image/entrypoint).
ENTRYPOINT ["docker-entrypoint.sh"]

# Production server: Gunicorn supervising Uvicorn workers (worker count from WEB_CONCURRENCY).
# Gunicorn is used over bare `uvicorn --workers` so its master-side `child_exit` hook can run
# the prometheus multiprocess worker-death cleanup — the piece `uvicorn --workers` cannot hook
# (gunicorn.conf.py). Migrations are applied by a separate one-shot step BEFORE this boots
# (compose `migrate` service / deployment runbook), never here.
CMD ["gunicorn", "app.main:app", "--config", "gunicorn.conf.py"]
