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
    # Uvicorn worker count — override per deployment (see CMD). Sized by CPU in prod.
    WEB_CONCURRENCY=2

# Least privilege: a dedicated non-root system user owns and runs the process.
RUN groupadd --system app && useradd --system --gid app --home-dir /app app

# Runtime artifacts only: the venv (with the installed package) and the alembic
# migration files, so the SAME image can run the app OR `alembic upgrade head`.
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

USER app

EXPOSE 8000

# Liveness probe hits /healthz (no dependencies, always fast). Uses stdlib urllib so no
# extra package (curl/wget) enters the image.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"

# Production server: no --reload, worker count from WEB_CONCURRENCY, bind all interfaces
# inside the container network. Migrations are applied by a separate one-shot step
# BEFORE this boots (compose `migrate` service / deployment runbook), never here.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-2}"]
