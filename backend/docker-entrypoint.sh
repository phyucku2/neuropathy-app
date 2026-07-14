#!/bin/sh
#
# Container entrypoint (ADR-0021). Its one job before starting the process: give the
# Prometheus multiprocess exposition a CLEAN shared directory on every fresh start.
#
# Stale per-worker metric files left over from a previous boot (e.g. a container restart
# reusing a mounted volume, or a crash that skipped worker-death cleanup) would be summed
# into the aggregated scrape and corrupt counters/gauges. So when PROMETHEUS_MULTIPROC_DIR
# is set we wipe and recreate it here, once, before any worker imports the metrics module
# and starts writing into it. When it is unset (single-process / dev) this is a no-op.
#
# `exec "$@"` hands off to the image CMD (gunicorn) or any override (e.g. `alembic upgrade
# head`), so the migration one-shot uses the SAME entrypoint unchanged.
set -e

if [ -n "${PROMETHEUS_MULTIPROC_DIR:-}" ]; then
  rm -rf "${PROMETHEUS_MULTIPROC_DIR}"
  mkdir -p "${PROMETHEUS_MULTIPROC_DIR}"
fi

exec "$@"
