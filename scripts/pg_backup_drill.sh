#!/usr/bin/env bash
#
# pg_backup_drill.sh — verify a Postgres backup by restoring it to a SCRATCH database
# (ADR-0021, docs/ops/backup-restore.md). An unverified backup is not a backup: this
# script performs a pg_dump -> pg_restore-to-scratch roundtrip and a read-back check, then
# tears the scratch copy down. It is SAFE by construction — it never writes to the source
# database and refuses to reuse an existing scratch database.
#
# SECRETS: connection details come from the environment (SOURCE_DSN, and libpq's standard
# PG* vars for the scratch admin connection). No password is ever written to disk or echoed.
# Never point SOURCE_DSN at production from a developer machine (CLAUDE.md §5); drills use
# SYNTHETIC data only.
#
# THE SECRET_STORE_KEY TRAP (see backup-restore.md): a DB dump holds only CIPHERTEXT for the
# EMR token vault. A restore is complete ONLY when paired with the matching-era
# SECRET_STORE_KEY, which must be backed up SEPARATELY from the database. This drill proves
# the DB half; the operator must separately confirm the key half (step printed at the end).
#
# Usage:
#   SOURCE_DSN="postgresql://postgres:PASSWORD@localhost:5432/neuropathy" \
#     scripts/pg_backup_drill.sh
#
# Optional env:
#   SCRATCH_DB   name of the throwaway restore target (default: neuropathy_drill_scratch)
#   ADMIN_DSN    admin/maintenance DSN used to create/drop SCRATCH_DB (default: derived
#                from SOURCE_DSN with the database swapped to 'postgres')
#   KEEP_SCRATCH if set to 1, do NOT drop the scratch DB (for manual inspection)

set -euo pipefail

: "${SOURCE_DSN:?Set SOURCE_DSN to the database to back up (synthetic data only)}"
SCRATCH_DB="${SCRATCH_DB:-neuropathy_drill_scratch}"
KEEP_SCRATCH="${KEEP_SCRATCH:-0}"

# Derive an admin DSN (points at the maintenance 'postgres' database) if not supplied, so
# createdb/dropdb do not need to connect through the database we are recreating.
if [[ -z "${ADMIN_DSN:-}" ]]; then
  ADMIN_DSN="$(python3 - "$SOURCE_DSN" <<'PY'
import sys
from urllib.parse import urlsplit, urlunsplit
u = urlsplit(sys.argv[1])
print(urlunsplit((u.scheme, u.netloc, "/postgres", "", "")))
PY
)"
fi

WORKDIR="$(mktemp -d)"
DUMP_FILE="${WORKDIR}/neuropathy-drill-$(date -u +%Y%m%dT%H%M%SZ).dump"

cleanup() {
  if [[ "$KEEP_SCRATCH" != "1" ]]; then
    psql --dbname="$ADMIN_DSN" -q -c "DROP DATABASE IF EXISTS \"${SCRATCH_DB}\"" >/dev/null 2>&1 || true
  fi
  rm -rf "$WORKDIR"
}
trap cleanup EXIT

echo "==> 1/5 Dumping source database (custom format, no owner/privileges)"
pg_dump --format=custom --no-owner --no-privileges --dbname="$SOURCE_DSN" --file="$DUMP_FILE"
echo "    dump written: $(du -h "$DUMP_FILE" | cut -f1) (kept only under $WORKDIR, removed on exit)"

echo "==> 2/5 Refusing to clobber an existing scratch database '$SCRATCH_DB'"
if psql --dbname="$ADMIN_DSN" -tAc \
     "SELECT 1 FROM pg_database WHERE datname = '${SCRATCH_DB}'" | grep -q 1; then
  echo "    ERROR: '$SCRATCH_DB' already exists — drop it or set SCRATCH_DB to a fresh name." >&2
  exit 1
fi

echo "==> 3/5 Creating scratch database and restoring into it"
psql --dbname="$ADMIN_DSN" -q -c "CREATE DATABASE \"${SCRATCH_DB}\""
SCRATCH_DSN="$(python3 - "$ADMIN_DSN" "$SCRATCH_DB" <<'PY'
import sys
from urllib.parse import urlsplit, urlunsplit
u = urlsplit(sys.argv[1])
print(urlunsplit((u.scheme, u.netloc, "/" + sys.argv[2], "", "")))
PY
)"
# --clean --if-exists keeps reruns idempotent; --no-owner ignores the dump's role grants.
pg_restore --clean --if-exists --no-owner --dbname="$SCRATCH_DSN" "$DUMP_FILE"

echo "==> 4/5 Read-back check on the restored scratch database"
TABLE_COUNT="$(psql --dbname="$SCRATCH_DSN" -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")"
echo "    restored public tables: ${TABLE_COUNT}"
if [[ "$TABLE_COUNT" -lt 1 ]]; then
  echo "    ERROR: restore produced no tables — the backup is NOT usable." >&2
  exit 1
fi

echo "==> 5/5 Drill complete."
echo "    NEXT (manual, cannot be automated here): confirm the SECRET_STORE_KEY from the"
echo "    SAME ERA as this dump is backed up SEPARATELY and decrypts a vaulted token — a"
echo "    DB restore without its matching key leaves every EMR token unrecoverable."
if [[ "$KEEP_SCRATCH" == "1" ]]; then
  echo "    KEEP_SCRATCH=1: scratch database '$SCRATCH_DB' left in place for inspection."
fi
