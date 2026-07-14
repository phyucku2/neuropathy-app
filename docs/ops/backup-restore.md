# Backup & restore drill

Postgres backup/restore for the neuropathy app, plus the one operational trap that will
silently make a restore useless. Decisions: **ADR-0018**. Storage model and durability:
`backend/README.md`, ADR-0017.

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

## Verify a restore (drill)

Practice restores on a schedule; an unverified backup is not a backup.

1. Restore the latest dump into a scratch database (steps above).
2. Boot the backend against it with the matching `SECRET_STORE_KEY`.
3. `GET /readyz` returns `200`.
4. Log in with a known **synthetic** account and confirm its trajectory/observations
   read back, and that an EMR connection's vaulted token still decrypts (proves the key
   pairing). Never use real patient data for the drill.
5. Record the drill outcome and tear down the scratch database and its dump copy.
