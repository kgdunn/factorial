#!/usr/bin/env bash
# ========================================================================
# restore-postgres.sh — restore a Postgres dump from S3-compatible
# object storage (Hetzner Object Storage by default) into the running
# stack, with admin_events logging.
#
#   *** THIS SCRIPT DESTROYS THE TARGET DATABASE ***
#
# Interactive confirmation is required unless --yes is passed.
# ========================================================================
#
# ONE-TIME OPERATOR SETUP: same as backup-postgres.sh. See that file's
# header + scripts/README.md. In short: awscli + jq + moreutils; a
# Hetzner bucket with credentials in ~/.aws/credentials (profile
# 'doe-backup'); S3_ENDPOINT_URL + S3_BUCKET in
# /etc/default/doe-backup.
#
# FLAGS:
#   --list                      print the most recent backups and exit
#   --key <s3key>               restore a specific S3 key (relative to bucket)
#   --yes                       skip interactive confirmation (for drills/scripts)
#   --target-db <name>          restore into this DB (default: $POSTGRES_DB)
#   --skip-stop-app             do not stop the app service (only valid with
#                               --target-db != $POSTGRES_DB — e.g. drills)
#   --dry-run                   download + verify sha, skip the actual restore
#   --verbose                   bash xtrace (passwords scrubbed)
#
# ENV (same as backup-postgres.sh):
#   REPO_DIR, S3_ENDPOINT_URL (required), S3_BUCKET (required), S3_PREFIX,
#   AWS_PROFILE, LOG_DIR, LOCK_FILE, HC_PING_URL, WEBHOOK_URL,
#   RESTORE_TIMEOUT (default: 3600)
# ========================================================================

set -Eeuo pipefail
IFS=$'\n\t'

: "${REPO_DIR:=/home/deploy/agentic-doe}"
: "${S3_PREFIX:=postgres}"
: "${AWS_PROFILE:=doe-backup}"
: "${RESTORE_TIMEOUT:=3600}"
: "${LOG_DIR:=/var/log/doe}"
: "${LOCK_FILE:=/var/lock/doe-restore.lock}"
: "${HC_PING_URL:=}"
: "${WEBHOOK_URL:=}"

LIST_ONLY=0
DRY_RUN=0
YES=0
SKIP_STOP_APP=0
VERBOSE=0
KEY=""
TARGET_DB=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --list) LIST_ONLY=1 ;;
        --key)  KEY="${2:?}"; shift ;;
        --yes)  YES=1 ;;
        --target-db) TARGET_DB="${2:?}"; shift ;;
        --skip-stop-app) SKIP_STOP_APP=1 ;;
        --dry-run) DRY_RUN=1 ;;
        --verbose) VERBOSE=1 ;;
        -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
    shift
done

if [[ -r /etc/default/doe-backup ]]; then
    # shellcheck disable=SC1091
    source /etc/default/doe-backup
fi
if [[ -r "$REPO_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$REPO_DIR/.env"
    set +a
fi

: "${POSTGRES_USER:?POSTGRES_USER not set (check $REPO_DIR/.env)}"
: "${POSTGRES_DB:?POSTGRES_DB not set (check $REPO_DIR/.env)}"
: "${S3_ENDPOINT_URL:?S3_ENDPOINT_URL is required}"
: "${S3_BUCKET:?S3_BUCKET is required}"

TARGET_DB="${TARGET_DB:-$POSTGRES_DB}"

if [[ "$SKIP_STOP_APP" == "1" && "$TARGET_DB" == "$POSTGRES_DB" ]]; then
    echo "--skip-stop-app is only valid when restoring into a non-primary DB" >&2
    exit 2
fi

if [[ "$VERBOSE" == "1" ]]; then
    PS4='+ [$(date -u +%H:%M:%S)] '
    set -x
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
HOSTNAME_SHORT="$(hostname -s)"
WORK_DIR="$(mktemp -d -t doe-restore-XXXXXX)"
mkdir -p "$LOG_DIR"
RUN_LOG="$LOG_DIR/restore-$STAMP.log"
: > "$RUN_LOG"

log()  { printf '[%s] [%-5s] %s\n' "$(date -u +%H:%M:%S)" "$1" "${*:2}" | tee -a "$RUN_LOG"; }
step() { log STEP "$*"; }
ok()   { log OK    "$*"; }
warn() { log WARN  "$*"; }
die()  { log ERROR "$*"; exit 1; }

aws_do() { aws --profile "$AWS_PROFILE" --endpoint-url "$S3_ENDPOINT_URL" "$@"; }

hc_ping() {
    [[ -n "$HC_PING_URL" ]] || return 0
    curl -fsS -m 10 --retry 2 -X POST --data-binary "${2:-}" \
        "${HC_PING_URL%/}${1}" >/dev/null 2>&1 || true
}

# ---- --list short-circuit ---------------------------------------------
if [[ "$LIST_ONLY" == "1" ]]; then
    for class in daily weekly monthly; do
        printf '\n=== %s/%s ===\n' "$S3_BUCKET" "$S3_PREFIX/$class"
        aws_do s3api list-objects-v2 \
            --bucket "$S3_BUCKET" --prefix "$S3_PREFIX/$class/" \
            --query 'reverse(sort_by(Contents, &LastModified))[:15].[LastModified, Size, Key]' \
            --output text 2>/dev/null || true
    done
    exit 0
fi

step "restore-postgres.sh starting"
log INFO "stamp=$STAMP host=$HOSTNAME_SHORT target_db=$TARGET_DB dry_run=$DRY_RUN"
log INFO "log_file=$RUN_LOG"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    die "another restore is already running (lock=$LOCK_FILE); aborting"
fi

# ---- Traps -------------------------------------------------------------
EVENT_ID=""
FINAL_STATUS="failed"
FINAL_ERROR=""
FINAL_PAYLOAD_MERGE_FILE=""

close_admin_event_via_cli() {
    [[ -n "$EVENT_ID" ]] || return 0
    local payload_json="{}"
    if [[ -n "$FINAL_PAYLOAD_MERGE_FILE" && -s "$FINAL_PAYLOAD_MERGE_FILE" ]]; then
        payload_json="$(cat "$FINAL_PAYLOAD_MERGE_FILE")"
    fi
    local -a cli_cmd=(docker compose exec -T app
        uv run python -m app.cli admin-event finish
        --id "$EVENT_ID" --status "$FINAL_STATUS"
        --payload-json "$payload_json")
    if [[ -n "$FINAL_ERROR" ]]; then
        cli_cmd+=(--error "$FINAL_ERROR")
    fi
    ( cd "$REPO_DIR" && "${cli_cmd[@]}" ) >>"$RUN_LOG" 2>&1
}

on_exit() {
    local rc=$?
    if [[ "$rc" -ne 0 ]]; then
        FINAL_STATUS="failed"
        [[ -z "$FINAL_ERROR" ]] && FINAL_ERROR="restore-postgres.sh exited with status $rc"
    fi

    if [[ -n "$EVENT_ID" ]]; then
        close_admin_event_via_cli || warn "CLI admin-event finish failed (non-fatal)"
    fi

    if [[ "$FINAL_STATUS" == "success" ]]; then
        hc_ping "" "$(tail -n 50 "$RUN_LOG" 2>/dev/null || true)"
    else
        hc_ping "/fail" "$(tail -n 200 "$RUN_LOG" 2>/dev/null || true)"
        if [[ -n "$WEBHOOK_URL" ]]; then
            curl -fsS -m 10 --retry 2 -H 'content-type: application/json' \
                -d "$(jq -nc --arg id "$EVENT_ID" --arg host "$HOSTNAME_SHORT" \
                            --arg err "$FINAL_ERROR" --arg key "$KEY" \
                            --arg log "$RUN_LOG" \
                           '{event_type:"postgres_restore",status:"failed",
                             event_id:$id,host:$host,error_message:$err,
                             s3_key_attempted:$key,log_path:$log}')" \
                "$WEBHOOK_URL" >/dev/null 2>&1 || true
        fi
    fi

    {
        echo "===== RESTORE SUMMARY ====="
        printf 'status:    %s\n' "${FINAL_STATUS^^}"
        printf 's3 key:    %s\n' "${KEY:-(none picked)}"
        printf 'target db: %s\n' "$TARGET_DB"
        printf 'event_id:  %s\n' "${EVENT_ID:-(not created)}"
        printf 'log file:  %s\n' "$RUN_LOG"
        [[ -n "$FINAL_ERROR" ]] && printf 'error:     %s\n' "$FINAL_ERROR"
        echo "==========================="
    } | tee -a "$RUN_LOG"

    rm -rf "$WORK_DIR"
    [[ -n "${FINAL_PAYLOAD_MERGE_FILE:-}" ]] && rm -f "$FINAL_PAYLOAD_MERGE_FILE"
    exit "$rc"
}
trap on_exit EXIT
trap 'FINAL_ERROR="line $LINENO: ${BASH_COMMAND//${POSTGRES_PASSWORD:-_NONE_}/<redacted>}"; exit 1' ERR

hc_ping "/start"

# ---- Preflight ---------------------------------------------------------
step "preflight: tooling"
for bin in aws jq docker sha256sum flock curl; do
    command -v "$bin" >/dev/null 2>&1 || die "missing tool: $bin"
done
docker compose version >/dev/null 2>&1 || die "docker compose v2 required"
ok "tooling present"

step "preflight: S3 credentials"
aws_do sts get-caller-identity >>"$RUN_LOG" 2>&1 \
    || die "aws sts get-caller-identity failed (profile=$AWS_PROFILE)"
aws_do s3api head-bucket --bucket "$S3_BUCKET" >>"$RUN_LOG" 2>&1 \
    || die "cannot head bucket $S3_BUCKET"
ok "S3 reachable"

step "preflight: postgres container health"
( cd "$REPO_DIR" && docker compose ps --status running postgres ) | grep -q postgres \
    || die "postgres container not running"
ok "postgres is up"

# ---- Pick the backup key ----------------------------------------------
if [[ -z "$KEY" ]]; then
    step "picking the latest backup under $S3_PREFIX/daily/"
    KEY=$(
        aws_do s3api list-objects-v2 \
            --bucket "$S3_BUCKET" --prefix "$S3_PREFIX/daily/" \
            --query 'sort_by(Contents, &Key)[-1].Key' --output text 2>/dev/null
    )
    [[ -n "$KEY" && "$KEY" != "None" ]] || die "no backups found under $S3_PREFIX/daily/"
fi
log INFO "picked key=$KEY"

# ---- Metadata ----------------------------------------------------------
step "fetching remote object metadata"
remote_json=$(aws_do s3api head-object --bucket "$S3_BUCKET" --key "$KEY" 2>>"$RUN_LOG") \
    || die "head-object failed for $KEY (does it exist?)"
REMOTE_SIZE=$(echo "$remote_json" | jq -r '.ContentLength')
REMOTE_SHA=$(echo "$remote_json" | jq -r '.Metadata.sha256 // empty')
BACKUP_ALEMBIC=$(echo "$remote_json" | jq -r '.Metadata.alembic // empty')
BACKUP_GIT=$(echo "$remote_json" | jq -r '.Metadata.git // empty')
log INFO "remote_size=$REMOTE_SIZE sha=$REMOTE_SHA alembic=$BACKUP_ALEMBIC git=$BACKUP_GIT"

# ---- Open admin_events row --------------------------------------------
step "recording admin_events.in_progress"
start_payload=$(jq -nc \
    --arg k "$KEY" --arg b "$S3_BUCKET" --arg ep "$S3_ENDPOINT_URL" \
    --arg tdb "$TARGET_DB" --arg a "$BACKUP_ALEMBIC" --arg h "$HOSTNAME_SHORT" \
    --arg log "$RUN_LOG" \
    '{s3_bucket:$b,s3_key:$k,s3_endpoint:$ep,target_db:$tdb,
      backup_alembic:$a,hostname:$h,log_path:$log}')
EVENT_ID=$(
    cd "$REPO_DIR" && docker compose exec -T app \
        uv run python -m app.cli admin-event start \
            --type postgres_restore \
            --source "manual@$HOSTNAME_SHORT" \
            --payload-json "$start_payload" 2>>"$RUN_LOG" | tr -d '[:space:]'
)
[[ -n "$EVENT_ID" ]] || die "could not open admin_events in_progress row"
ok "admin_events id=$EVENT_ID"

# ---- Download + sha ----------------------------------------------------
step "downloading to $WORK_DIR/restore.dump"
aws_do s3 cp "s3://$S3_BUCKET/$KEY" "$WORK_DIR/restore.dump" --no-progress >>"$RUN_LOG" 2>&1
LOCAL_SIZE=$(stat -c%s "$WORK_DIR/restore.dump")
LOCAL_SHA=$(sha256sum "$WORK_DIR/restore.dump" | awk '{print $1}')
(( LOCAL_SIZE == REMOTE_SIZE )) || die "download size mismatch: $LOCAL_SIZE vs $REMOTE_SIZE"
if [[ -n "$REMOTE_SHA" ]]; then
    [[ "$LOCAL_SHA" == "$REMOTE_SHA" ]] || die "sha mismatch: local=$LOCAL_SHA remote=$REMOTE_SHA"
    ok "sha256 verified ($LOCAL_SHA)"
else
    warn "remote had no sha256 metadata — skipped equality check"
fi

# ---- Alembic compatibility check --------------------------------------
step "alembic compatibility check"
CURRENT_ALEMBIC=$(
    cd "$REPO_DIR" && docker compose exec -T app uv run alembic current 2>>"$RUN_LOG" \
        | awk 'NF{print $1; exit}'
)
log INFO "current_alembic=$CURRENT_ALEMBIC  backup_alembic=$BACKUP_ALEMBIC"
if [[ -n "$BACKUP_ALEMBIC" && -n "$CURRENT_ALEMBIC" && "$BACKUP_ALEMBIC" != "$CURRENT_ALEMBIC" ]]; then
    warn "alembic mismatch: current=$CURRENT_ALEMBIC backup=$BACKUP_ALEMBIC"
    if [[ "$YES" != "1" ]]; then
        die "refusing to continue without --yes when alembic heads differ"
    fi
fi

# ---- Dry-run short-circuit --------------------------------------------
if [[ "$DRY_RUN" == "1" ]]; then
    step "dry-run: skipping actual restore"
    FINAL_STATUS="success"
    FINAL_PAYLOAD_MERGE_FILE="$WORK_DIR/payload.json"
    jq -nc --arg mode "dry_run" --arg sha "$LOCAL_SHA" --argjson sz "$LOCAL_SIZE" \
        '{mode:$mode,sha256:$sha,size_bytes:$sz}' > "$FINAL_PAYLOAD_MERGE_FILE"
    ok "dry-run complete"
    exit 0
fi

# ---- Interactive confirmation -----------------------------------------
if [[ "$YES" != "1" ]]; then
    cat <<EOF

  You are about to REPLACE database '$TARGET_DB' with:
    s3://$S3_BUCKET/$KEY
    size: $LOCAL_SIZE bytes  sha256: $LOCAL_SHA
    backup alembic head: ${BACKUP_ALEMBIC:-(unknown)}
    backup git sha:      ${BACKUP_GIT:-(unknown)}

  Current '$TARGET_DB' contents will be DROPPED.

  Type exactly:  RESTORE $TARGET_DB
EOF
    printf '> '
    read -r confirmation
    [[ "$confirmation" == "RESTORE $TARGET_DB" ]] || die "confirmation mismatch; aborting"
fi

# ---- Stop app (unless drill) ------------------------------------------
if [[ "$SKIP_STOP_APP" == "0" ]]; then
    step "stopping app service"
    ( cd "$REPO_DIR" && docker compose stop app ) >>"$RUN_LOG" 2>&1
    ok "app stopped"
fi

# ---- Drop + recreate target DB ----------------------------------------
step "dropping + recreating database '$TARGET_DB'"
( cd "$REPO_DIR" && docker compose exec -T postgres \
    psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
    -v tdb="$TARGET_DB" -v owner="$POSTGRES_USER" <<'SQL' >>"$RUN_LOG" 2>&1
SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
 WHERE datname = :'tdb' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS :"tdb";
CREATE DATABASE :"tdb" OWNER :"owner";
SQL
)
ok "database recreated"

# ---- pg_restore --------------------------------------------------------
step "pg_restore → $TARGET_DB"
timeout "$RESTORE_TIMEOUT" bash -c '
    cd "$1" && docker compose exec -T postgres \
        pg_restore -U "$2" -d "$3" \
        --no-owner --no-privileges --exit-on-error --jobs=2
' _ "$REPO_DIR" "$POSTGRES_USER" "$TARGET_DB" < "$WORK_DIR/restore.dump" \
    >>"$RUN_LOG" 2>&1 \
    || die "pg_restore failed"
ok "pg_restore complete"

# ---- Restart app + alembic upgrade (primary only) ---------------------
if [[ "$SKIP_STOP_APP" == "0" ]]; then
    step "starting app + running alembic upgrade head"
    ( cd "$REPO_DIR" && docker compose start app ) >>"$RUN_LOG" 2>&1
    ( cd "$REPO_DIR" && docker compose exec -T app \
        uv run alembic upgrade head ) >>"$RUN_LOG" 2>&1 \
        || die "alembic upgrade failed"
    ok "alembic upgraded"
fi

# ---- Smoke test --------------------------------------------------------
step "smoke test"
SMOKE=$(
    cd "$REPO_DIR" && docker compose exec -T postgres \
        psql -tAqX -U "$POSTGRES_USER" -d "$TARGET_DB" \
        -c 'SELECT count(*) FROM users;' 2>/dev/null | tr -d '[:space:]' || echo "?"
)
log INFO "users_count=$SMOKE"

POST_ALEMBIC=""
if [[ "$SKIP_STOP_APP" == "0" ]]; then
    POST_ALEMBIC=$(
        cd "$REPO_DIR" && docker compose exec -T app uv run alembic current 2>/dev/null \
            | awk 'NF{print $1; exit}'
    )
fi

FINAL_STATUS="success"
FINAL_PAYLOAD_MERGE_FILE="$WORK_DIR/payload.json"
jq -nc \
    --arg b "$S3_BUCKET" --arg k "$KEY" --arg ep "$S3_ENDPOINT_URL" \
    --arg sha "$LOCAL_SHA" --arg bal "$BACKUP_ALEMBIC" \
    --arg pal "$POST_ALEMBIC" --arg tdb "$TARGET_DB" \
    --arg host "$HOSTNAME_SHORT" --arg log "$RUN_LOG" --arg smoke "$SMOKE" \
    --argjson sz "$LOCAL_SIZE" \
    '{s3_bucket:$b,s3_key:$k,s3_endpoint:$ep,size_bytes:$sz,sha256:$sha,
      backup_alembic:$bal,post_alembic:$pal,target_db:$tdb,
      hostname:$host,log_path:$log,smoke_users_count:$smoke}' \
    > "$FINAL_PAYLOAD_MERGE_FILE"
ok "restore succeeded"
