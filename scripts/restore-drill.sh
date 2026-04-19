#!/usr/bin/env bash
# ========================================================================
# restore-drill.sh — weekly sanity check that backups are restorable.
#
# Flow:
#   1. Find the newest object under postgres/daily/ in S3.
#   2. Call restore-postgres.sh with --yes --target-db doe_db_drill
#      --skip-stop-app --key <latest>  so production is untouched.
#   3. Run a smoke query (row counts on users + conversations).
#   4. DROP the scratch database.
#   5. Log a 'restore_drill' event to admin_events with the results.
#
# Cron target: see deploy/cron/doe-backup.cron (weekly, Mon 04:30 UTC).
# ========================================================================

set -Eeuo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

if [[ -r /etc/default/doe-backup ]]; then
    # shellcheck disable=SC1091
    source /etc/default/doe-backup
fi

: "${REPO_DIR:=/home/deploy/agentic-doe}"
: "${S3_PREFIX:=postgres}"
: "${AWS_PROFILE:=doe-backup}"
: "${LOG_DIR:=/var/log/doe}"
: "${DRILL_DB:=doe_db_drill}"

if [[ -r "$REPO_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$REPO_DIR/.env"
    set +a
fi

: "${S3_ENDPOINT_URL:?S3_ENDPOINT_URL is required}"
: "${S3_BUCKET:?S3_BUCKET is required}"
: "${POSTGRES_USER:?POSTGRES_USER not set}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
HOSTNAME_SHORT="$(hostname -s)"
mkdir -p "$LOG_DIR"
RUN_LOG="$LOG_DIR/drill-$STAMP.log"
: > "$RUN_LOG"

log() { printf '[%s] [%-5s] %s\n' "$(date -u +%H:%M:%S)" "$1" "${*:2}" | tee -a "$RUN_LOG"; }

aws_do() { aws --profile "$AWS_PROFILE" --endpoint-url "$S3_ENDPOINT_URL" "$@"; }

# ---- Open admin_events row --------------------------------------------
cd "$REPO_DIR"
EVENT_ID=$(
    docker compose exec -T app \
        uv run python -m app.cli admin-event start \
            --type restore_drill \
            --source "cron@$HOSTNAME_SHORT" \
            --payload-json "$(jq -nc --arg h "$HOSTNAME_SHORT" --arg l "$RUN_LOG" \
                                   '{hostname:$h,log_path:$l}')" \
        2>>"$RUN_LOG" | tr -d '[:space:]'
)

close_event() {
    local status="$1" err="${2:-}" payload_json="${3:-{\}}"
    local -a cmd=(docker compose exec -T app
        uv run python -m app.cli admin-event finish
        --id "$EVENT_ID" --status "$status"
        --payload-json "$payload_json")
    [[ -n "$err" ]] && cmd+=(--error "$err")
    ( cd "$REPO_DIR" && "${cmd[@]}" ) >>"$RUN_LOG" 2>&1 || true
}

fail() {
    local err="$1"
    log ERROR "$err"
    close_event failed "$err"
    exit 1
}

# ---- Pick newest daily backup -----------------------------------------
log STEP "picking newest daily backup"
LATEST_KEY=$(
    aws_do s3api list-objects-v2 \
        --bucket "$S3_BUCKET" --prefix "$S3_PREFIX/daily/" \
        --query 'sort_by(Contents, &Key)[-1].Key' --output text 2>/dev/null
)
[[ -n "$LATEST_KEY" && "$LATEST_KEY" != "None" ]] || fail "no daily backups found"
log INFO "latest_key=$LATEST_KEY"

# ---- Run restore into scratch DB --------------------------------------
log STEP "restoring $LATEST_KEY into $DRILL_DB"
"$REPO_DIR/scripts/restore-postgres.sh" \
    --yes --target-db "$DRILL_DB" --skip-stop-app --key "$LATEST_KEY" \
    >>"$RUN_LOG" 2>&1 \
    || fail "restore-postgres.sh failed for $LATEST_KEY"

# ---- Smoke queries ----------------------------------------------------
log STEP "running smoke queries"
USERS_COUNT=$(
    docker compose exec -T postgres \
        psql -tAqX -U "$POSTGRES_USER" -d "$DRILL_DB" \
        -c 'SELECT count(*) FROM users;' 2>/dev/null | tr -d '[:space:]' || echo "?"
)
CONV_COUNT=$(
    docker compose exec -T postgres \
        psql -tAqX -U "$POSTGRES_USER" -d "$DRILL_DB" \
        -c 'SELECT count(*) FROM conversations;' 2>/dev/null | tr -d '[:space:]' || echo "?"
)
log INFO "users_count=$USERS_COUNT conversations_count=$CONV_COUNT"

# ---- Drop the scratch DB ----------------------------------------------
log STEP "dropping scratch database $DRILL_DB"
docker compose exec -T postgres \
    psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
    -v tdb="$DRILL_DB" <<'SQL' >>"$RUN_LOG" 2>&1 \
    || fail "failed to drop scratch database"
SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
 WHERE datname = :'tdb' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS :"tdb";
SQL

close_event success "" "$(jq -nc \
    --arg key "$LATEST_KEY" --arg users "$USERS_COUNT" \
    --arg conv "$CONV_COUNT" --arg host "$HOSTNAME_SHORT" \
    --arg log "$RUN_LOG" --arg db "$DRILL_DB" \
    '{source_s3_key:$key,drill_target_db:$db,users_count:$users,
      conversations_count:$conv,hostname:$host,log_path:$log}')"

log OK "restore drill succeeded"
