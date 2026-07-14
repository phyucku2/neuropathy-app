# Backup & restore drill

Postgres backup/restore for the neuropathy app, plus the one operational trap that will
silently make a restore useless. Decisions: **ADR-0018**, **ADR-0021** (the scripted
verification drill). Storage model and durability: `backend/README.md`, ADR-0017.

## ⚠️ The `SECRET_STORE_KEY` trap (read this first)

EMR OAuth tokens are stored **encrypted at rest** in the database `secret` table, using
the Fernet key in `SECRET_STORE_KEY` (ADR-0017). The database backup contains only the
**ciphertext**. The key is **not** in the database.

**If you back up the database but lose `SECRET_STORE_KEY`, every vaulted token in that
backup is permanently unrecoverable** — a restore yields undecryptable rows, and every
EMR connection must be re-authorized from scratch.

Therefore:

- Back up `SECRET_STORE_KEY` **separately from the database**, in a secret manager /
  key vault — never in the same store, snapshot, or bucket as the DB dump (a single
  compromise must not yield both ciphertext and key, and a single loss must not take
  both).
- Treat key rotation as a migration: re-encrypt existing rows under the new key before
  retiring the old one, and keep the old key until re-encryption is confirmed.
- The same applies to `JWT_SECRET` (its loss invalidates all issued sessions — less
  catastrophic, but plan for it) and, less severely, `OPS_BOOTSTRAP_TOKEN`.

A database restore is only complete when paired with the **matching** `SECRET_STORE_KEY`
from the same era.

## PHI handling of backups

Database dumps contain **PHI** (patient records, observations, audit log). Handle every
dump under the same posture as the live database (CLAUDE.md §5, HIPAA):

- Encrypt dumps at rest and in transit; store them in an access-controlled,
  audit-logged location; apply least privilege.
- Set and enforce a retention/expiry policy; securely destroy expired dumps.
- Never copy a production dump onto a developer laptop or into this repo. Non-production
  environments use **synthetic** data only.

## Backup (`pg_dump`)

Logical dump of a single database (custom format — compressed, supports selective
`pg_restore`):

```bash
pg_dump \
  --format=custom \
  --no-owner --no-privileges \
  --dbname="postgresql://USER:PASSWORD@HOST:5432/DB" \
  --file="neuropathy-$(date -u +%Y%m%dT%H%M%SZ).dump"
```

Then, in your secret manager (NOT next to the dump), snapshot the current
`SECRET_STORE_KEY` (and `JWT_SECRET`) value with the same timestamp so the pair is
recoverable together.

For the compose topology:

```bash
docker compose exec -T db \
  pg_dump --format=custom --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB" \
  > "neuropathy-$(date -u +%Y%m%dT%H%M%SZ).dump"
```

## Restore (`pg_restore`)

Restore into a **fresh, empty** database, then bring the schema to head and boot with the
matching key.

```bash
# 1. Create an empty target database (do not restore over a live one).
createdb --dbname="postgresql://USER:PASSWORD@HOST:5432/postgres" neuropathy_restored

# 2. Restore. --clean --if-exists makes reruns idempotent; --no-owner ignores the dump's
#    role grants (roles are provisioned by the platform, not the dump).
pg_restore \
  --clean --if-exists --no-owner \
  --dbname="postgresql://USER:PASSWORD@HOST:5432/neuropathy_restored" \
  neuropathy-<timestamp>.dump

# 3. Bring the schema to head (a dump may predate the current migrations). Same image.
docker run --rm -e DATABASE_URL="postgresql+asyncpg://USER:PASSWORD@HOST:5432/neuropathy_restored" \
  neuropathy-backend:<tag> alembic upgrade head

# 4. Boot the app against the restored DB with the SECRET_STORE_KEY *from the same era*
#    as the dump, then verify readiness.
curl -fsS http://BACKEND:8000/readyz
```

## Verify a restore (scripted drill)

Practice restores on a schedule; an unverified backup is not a backup. The repo ships a
concrete, tested drill script that performs a `pg_dump` → `pg_restore`-to-scratch roundtrip
with a read-back check, then tears the scratch copy down. It is **safe by construction**: it
never writes to the source database and refuses to clobber an existing scratch database.

```bash
# Runs a full dump/restore roundtrip against a THROWAWAY scratch database, then drops it.
# SOURCE_DSN uses SYNTHETIC data only — never point it at production from a laptop.
SOURCE_DSN="postgresql://USER:PASSWORD@HOST:5432/neuropathy" \
  scripts/pg_backup_drill.sh
```

The script (`scripts/pg_backup_drill.sh`, ADR-0021):

1. `pg_dump` the source to a custom-format dump under a temp dir (removed on exit).
2. Refuse to proceed if the scratch database already exists (no silent clobber).
3. Create the scratch database and `pg_restore` the dump into it.
4. Read-back check: assert the restore produced ≥1 public table (a zero-table restore fails
   the drill loudly).
5. Tear down the scratch database and the dump copy (`KEEP_SCRATCH=1` leaves the scratch DB
   for manual inspection).

Connection details come only from the environment (`SOURCE_DSN`, and libpq's standard `PG*`
vars for the scratch admin connection); **no password is written to disk or echoed**.

### Full end-to-end drill (with the app + the key)

The script proves the **database** half. A complete drill also proves the
`SECRET_STORE_KEY` pairing that the script cannot automate:

1. Run `scripts/pg_backup_drill.sh` (or restore the latest dump into a scratch DB manually).
2. Boot the backend against the scratch DB with the `SECRET_STORE_KEY` **from the same era**
   as the dump.
3. `GET /readyz` returns `200`; `GET /metrics` renders (both PHI-free — ADR-0021).
4. Log in with a known **synthetic** account and confirm its trajectory/observations read
   back, and that an EMR connection's vaulted token still decrypts (proves the key
   pairing). Never use real patient data for the drill.
5. Record the drill outcome and tear down the scratch database and its dump copy.

### Manual-verification checklist (when a scripted drill isn't possible)

- [ ] A dump exists from within the retention window and is stored encrypted, access-logged.
- [ ] The matching-era `SECRET_STORE_KEY` (and `JWT_SECRET`) is backed up **separately** and
      retrievable.
- [ ] A test restore into a scratch DB completed within the last review period.
- [ ] Post-restore: `/readyz` 200, a synthetic account reads back, a vaulted token decrypts.
- [ ] Scratch DB and dump copies were destroyed after the drill; outcome recorded.
