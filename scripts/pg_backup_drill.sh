#!/usr/bin/env bash
#
# pg_backup_drill.sh — verify a Postgres backup by restoring it to a SCRATCH database
# (ADR-0021, docs/ops/backup-restore.md). An unverified backup is not a backup: this
# script performs a pg_dump -> pg_restore-to-scratch roundtrip and a read-back check, then
# tears the scratch copy down. It is SAFE by construction — it never writes to the source
# database and refuses to reuse an existing scratch database.
#
# CREDENTIALS — never in argv. The connection details arrive as DSN env vars (SOURCE_DSN,
# and optionally ADMIN_DSN). This script parses them and hands the tools their credentials
# ONLY via libpq's environment/PGPASSFILE mechanism, never on a command line:
#   - The password is written to a 0600 `.pgpass` file inside a mktemp workdir and exposed
#     via PGPASSFILE; it is NEVER passed to pg_dump/psql/pg_restore, nor to the python
#     parser (the DSNs are read from the environment, not argv). So it never appears in
#     `ps`/`/proc/<pid>/cmdline` for any process this script spawns.
#   - Host/port/user go through PGHOST/PGPORT/PGUSER; only plain, non-secret database NAMES
#     appear as `--dbname=` arguments.
#   - The `.pgpass` file and the whole workdir are removed on exit (trap below).
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
# Default the admin DSN to the source server's maintenance 'postgres' database, so
# createdb/dropdb do not need to connect through the database we are recreating. Passed to
# the parser via the environment (never argv).
export ADMIN_DSN="${ADMIN_DSN:-}"

WORKDIR="$(mktemp -d)"
DUMP_FILE="${WORKDIR}/neuropathy-drill-$(date -u +%Y%m%dT%H%M%SZ).dump"
export PGPASSFILE="${WORKDIR}/.pgpass"

cleanup() {
  if [[ "$KEEP_SCRATCH" != "1" ]]; then
    PGHOST="$ADM_HOST" PGPORT="$ADM_PORT" PGUSER="$ADM_USER" \
      psql --dbname="$ADM_DB" -q -c "DROP DATABASE IF EXISTS \"${SCRATCH_DB}\"" >/dev/null 2>&1 || true
  fi
  rm -rf "$WORKDIR"
}
trap cleanup EXIT

# Parse SOURCE_DSN (and ADMIN_DSN, defaulted to source@/postgres) WITHOUT putting either on
# a command line: the parser reads them from the environment, writes the 0600 PGPASSFILE
# (password never leaves this file), and prints only NON-secret connection facts to eval.
eval "$(PGPASSFILE="$PGPASSFILE" python3 <<'PY'
import os
from urllib.parse import urlsplit, unquote


def parse(dsn: str) -> dict[str, str]:
    u = urlsplit(dsn)
    return {
        "host": unquote(u.hostname or "localhost"),
        "port": str(u.port or 5432),
        "user": unquote(u.username or ""),
        "password": unquote(u.password or ""),
        "db": unquote(u.path.lstrip("/")) or "postgres",
    }


src = parse(os.environ["SOURCE_DSN"])
admin_dsn = os.environ.get("ADMIN_DSN") or ""
if admin_dsn:
    adm = parse(admin_dsn)
else:
    # Derive: same server/credentials as the source, maintenance 'postgres' database.
    adm = dict(src, db="postgres")

# Password only ever lands in this 0600 file (host:port:*:user:password), matching any
# database on that host/user so the scratch DB (not yet created) authenticates too. Fields
# escape libpq's `.pgpass` metacharacters (`\` and `:`).
def esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:")


lines = []
for c in (src, adm):
    if c["password"]:
        lines.append(f'{esc(c["host"])}:{c["port"]}:*:{esc(c["user"])}:{esc(c["password"])}')
path = os.environ["PGPASSFILE"]
with open(path, "w", encoding="utf-8") as fh:
    fh.write("\n".join(dict.fromkeys(lines)) + ("\n" if lines else ""))
os.chmod(path, 0o600)

# Emit only non-secret facts for the shell to eval: host/port/user/dbname are simple
# identifiers (no password among them), single-quoted defensively.
for prefix, c in (("SRC", src), ("ADM", adm)):
    for key in ("host", "port", "user", "db"):
        print(f"{prefix}_{key.upper()}='{c[key]}'")
PY
)"

echo "==> 1/5 Dumping source database (custom format, no owner/privileges)"
PGHOST="$SRC_HOST" PGPORT="$SRC_PORT" PGUSER="$SRC_USER" \
  pg_dump --format=custom --no-owner --no-privileges --dbname="$SRC_DB" --file="$DUMP_FILE"
echo "    dump written: $(du -h "$DUMP_FILE" | cut -f1) (kept only under $WORKDIR, removed on exit)"

echo "==> 2/5 Refusing to clobber an existing scratch database '$SCRATCH_DB'"
if PGHOST="$ADM_HOST" PGPORT="$ADM_PORT" PGUSER="$ADM_USER" \
     psql --dbname="$ADM_DB" -tAc \
     "SELECT 1 FROM pg_database WHERE datname = '${SCRATCH_DB}'" | grep -q 1; then
  echo "    ERROR: '$SCRATCH_DB' already exists — drop it or set SCRATCH_DB to a fresh name." >&2
  exit 1
fi

echo "==> 3/5 Creating scratch database and restoring into it"
PGHOST="$ADM_HOST" PGPORT="$ADM_PORT" PGUSER="$ADM_USER" \
  psql --dbname="$ADM_DB" -q -c "CREATE DATABASE \"${SCRATCH_DB}\""
# --clean --if-exists keeps reruns idempotent; --no-owner ignores the dump's role grants.
# The scratch DB is on the admin server; its plain NAME is the only connection arg.
PGHOST="$ADM_HOST" PGPORT="$ADM_PORT" PGUSER="$ADM_USER" \
  pg_restore --clean --if-exists --no-owner --dbname="$SCRATCH_DB" "$DUMP_FILE"

echo "==> 4/5 Read-back check on the restored scratch database"
TABLE_COUNT="$(PGHOST="$ADM_HOST" PGPORT="$ADM_PORT" PGUSER="$ADM_USER" \
  psql --dbname="$SCRATCH_DB" -tAc \
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
