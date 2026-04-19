# Operational scripts

Daily Postgres backup + restore tooling for this repo. Installed on the
VPS and invoked from cron. Neo4j is **out of scope**.

## What's in here

| file | purpose |
|---|---|
| `backup-postgres.sh` | preflight → dump → upload → verify → log |
| `restore-postgres.sh` | list / download / verify / restore from S3 |
| `cron-backup-wrapper.sh` | cron shim: PATH, `/etc/default/doe-backup`, `chronic` |
| `restore-drill.sh` | weekly: restore newest backup to scratch DB, smoke-query, drop |
| `prune-old-run-logs.sh` | safety net for run-log cleanup if logrotate isn't present |

Every script records its run history in the `admin_events` table (see
`backend/alembic/versions/0002_admin_events.py`). Rows go from
`in_progress` → `success` / `failed`, with a rich JSONB `payload`
(S3 key, size, sha256, alembic head, git sha, log path, …).

## One-time operator setup

This section is the full runbook. Do it **once** per VPS.

### 1. Install tooling on the host

```bash
sudo apt-get install -y awscli jq moreutils
aws --version
jq --version
chronic --version    # from moreutils
docker compose version
```

### 2. Create the Hetzner Object Storage bucket

In the Hetzner Cloud Console → **Object Storage**:

1. **Create a bucket** (e.g. `doe-db-backups-prod`) in the same region
   as your CX32 VPS (Falkenstein `fsn1` or Nuremberg `nbg1`). Internal
   traffic within the same region is free.
2. Turn **Object Lock** on (compliance mode) with a retention window
   of **at least 400 days** (that's the monthly retention class).
   This makes backups write-once-read-many — an attacker with stolen
   credentials cannot delete or overwrite them within the window.
3. Under **Access credentials** generate an access key + secret
   scoped to this bucket only.
4. Configure **lifecycle rules** (GFS — grandfather/father/son):

   | prefix | expire after |
   |---|---|
   | `postgres/daily/` | 35 days |
   | `postgres/weekly/` | 100 days |
   | `postgres/monthly/` | 400 days |

   Sample rule JSON (paste into Hetzner Console → Lifecycle editor,
   one rule per prefix):

   ```json
   {
     "Rules": [
       {
         "ID": "expire-daily",
         "Status": "Enabled",
         "Filter": { "Prefix": "postgres/daily/" },
         "Expiration": { "Days": 35 }
       },
       {
         "ID": "expire-weekly",
         "Status": "Enabled",
         "Filter": { "Prefix": "postgres/weekly/" },
         "Expiration": { "Days": 100 }
       },
       {
         "ID": "expire-monthly",
         "Status": "Enabled",
         "Filter": { "Prefix": "postgres/monthly/" },
         "Expiration": { "Days": 400 }
       }
     ]
   }
   ```

### 3. Store credentials on the VPS

As the `deploy` user (not root):

```bash
sudo -iu deploy
mkdir -p ~/.aws && chmod 700 ~/.aws

cat > ~/.aws/credentials <<'EOF'
[doe-backup]
aws_access_key_id     = <KEY-FROM-HETZNER>
aws_secret_access_key = <SECRET-FROM-HETZNER>
EOF
chmod 600 ~/.aws/credentials

cat > ~/.aws/config <<'EOF'
[profile doe-backup]
region = eu-central-1
output = json
EOF
chmod 600 ~/.aws/config
```

Hetzner ignores the AWS region, but the CLI profile needs *some* value.

### 4. Create `/etc/default/doe-backup`

Copy the template shipped at `deploy/etc-default/doe-backup.example`
into place and fill it in:

```bash
sudo cp /home/deploy/agentic-doe/deploy/etc-default/doe-backup.example \
        /etc/default/doe-backup
sudo chown root:root /etc/default/doe-backup
sudo chmod 0644 /etc/default/doe-backup
sudoedit /etc/default/doe-backup
```

At minimum:

```
S3_ENDPOINT_URL=https://fsn1.your-objectstorage.com
S3_BUCKET=doe-db-backups-prod
AWS_PROFILE=doe-backup
REPO_DIR=/home/deploy/agentic-doe
```

Optional but recommended:

```
HC_PING_URL=https://hc-ping.com/<uuid>        # healthchecks.io
WEBHOOK_URL=https://hooks.slack.com/services/... # failure alerts
```

### 5. Smoke test

```bash
cd /home/deploy/agentic-doe
./scripts/backup-postgres.sh --dry-run   # no side effects
./scripts/backup-postgres.sh             # real run; ~1 min
```

Verify:

- `./var/log/doe/backup-*.log` (or wherever `LOG_DIR` points) has a
  `===== BACKUP SUMMARY =====` at the end showing `status: SUCCESS`.
- The `admin_events` table has two rows for `postgres_backup` — one
  `in_progress` (inserted at step "record") and one `success` (the
  same row, updated at the end) with a full payload.
- The S3 bucket has a new `.dump` under `postgres/daily/YYYY/MM/DD/`.
- Optional: `./scripts/restore-postgres.sh --list` shows that key.

### 6. Install cron + logrotate

```bash
sudo cp /home/deploy/agentic-doe/deploy/cron/doe-backup.cron /etc/cron.d/doe-backup
sudo chown root:root /etc/cron.d/doe-backup
sudo chmod 0644 /etc/cron.d/doe-backup

sudo cp /home/deploy/agentic-doe/deploy/logrotate/doe-backup /etc/logrotate.d/doe-backup
sudo chown root:root /etc/logrotate.d/doe-backup
sudo chmod 0644 /etc/logrotate.d/doe-backup

sudo mkdir -p /var/log/doe
sudo chown deploy:deploy /var/log/doe
```

The cron schedule is (all times UTC):

| when | what |
|---|---|
| daily 03:07 | `backup-postgres.sh daily` |
| Sun 03:30 | `backup-postgres.sh weekly` |
| 1st of month 04:00 | `backup-postgres.sh monthly` |
| Mon 04:30 | `restore-drill.sh` |

## Day-2 operations

### Tail the admin event history

```sql
SELECT created_at, event_type, status,
       payload->>'s3_key' AS s3_key,
       duration_ms,
       error_message
  FROM admin_events
 WHERE event_type IN ('postgres_backup','postgres_restore','restore_drill')
 ORDER BY created_at DESC
 LIMIT 20;
```

### Manual backup / restore commands

```bash
# Manual ad-hoc backup (daily class)
./scripts/backup-postgres.sh

# List recent backups
./scripts/restore-postgres.sh --list

# Restore latest (interactive RESTORE <db> confirmation)
./scripts/restore-postgres.sh

# Restore a specific key
./scripts/restore-postgres.sh --key postgres/daily/2026/04/19/doe_db-20260419T030703Z-a1b2c3d.dump

# Dry-run: download + sha verify, do NOT restore
./scripts/restore-postgres.sh --dry-run

# Run the restore drill manually (safe, uses scratch DB)
./scripts/restore-drill.sh
```

### If something fails

1. Look at the per-run log in `/var/log/doe/backup-<stamp>.log`.
2. Check `admin_events` for the corresponding `failed` row — the
   `error_message` column has the short summary, `payload.log_path`
   has the full log path.
3. healthchecks.io (if configured) shows missed runs — that's the
   only signal for "cron died" / "host offline".
