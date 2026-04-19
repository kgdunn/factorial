#!/usr/bin/env bash
# ========================================================================
# backup-postgres.sh — daily Postgres backup to S3-compatible object
# storage (Hetzner Object Storage by default) with admin_events logging.
# ========================================================================
#
# ONE-TIME OPERATOR SETUP (do this once per VPS, before enabling cron):
#
#   1. Install tooling on the host:
#        sudo apt-get install -y awscli jq moreutils
#      (verify: aws --version ; jq --version ; chronic --version ;
#       docker compose version)
#
#   2. In the Hetzner Cloud Console → Object Storage:
#        - Create a bucket, e.g. 'doe-db-backups-prod', in the same
#          region as the VPS (Falkenstein fsn1 or Nuremberg nbg1).
#          Internal traffic in the same region is free.
#        - Turn Object Lock ON (compliance mode) with a retention
#          window >= 400 days so WORM protects the monthly class.
#        - Under "Access credentials" generate an access key + secret
#          scoped to this bucket only.
#        - Configure lifecycle rules to enforce GFS retention:
#            prefix postgres/daily/    → expire after 35 days
#            prefix postgres/weekly/   → expire after 100 days
#            prefix postgres/monthly/  → expire after 400 days
#          See scripts/README.md for sample JSON.
#
#   3. Store credentials on the VPS as the 'deploy' user:
#        sudo -iu deploy
#        mkdir -p ~/.aws && chmod 700 ~/.aws
#        cat > ~/.aws/credentials <<'EOF'
#        [doe-backup]
#        aws_access_key_id     = <KEY>
#        aws_secret_access_key = <SECRET>
#        EOF
#        chmod 600 ~/.aws/credentials
#        cat > ~/.aws/config <<'EOF'
#        [profile doe-backup]
#        region = eu-central-1
#        output = json
#        EOF
#        chmod 600 ~/.aws/config
#      (Hetzner doesn't care about AWS region, but the profile needs
#       one. Any value is fine.)
#
#   4. Create /etc/default/doe-backup (shipped as
#      deploy/etc-default/doe-backup.example) with at minimum:
#        S3_ENDPOINT_URL=https://fsn1.your-objectstorage.com
#        S3_BUCKET=doe-db-backups-prod
#        AWS_PROFILE=doe-backup
#      Optional:
#        HC_PING_URL=https://hc-ping.com/<uuid>
#        WEBHOOK_URL=https://hooks.slack.com/services/...
#
#   5. Smoke test once, verbosely:
#        ./scripts/backup-postgres.sh --dry-run
#        ./scripts/backup-postgres.sh
#      Confirm the run log at $LOG_DIR/backup-<stamp>.log and the new
#      row in admin_events (via 'docker compose exec postgres psql').
#
#   6. Install cron from deploy/cron/doe-backup.cron — see README.
#
# CONFIG KNOBS (env vars; documented defaults in DEFAULTS block below):
#   REPO_DIR          path to the checkout (default: /home/deploy/agentic-doe)
#   S3_ENDPOINT_URL   S3-compatible endpoint (REQUIRED — no default)
#   S3_BUCKET         target bucket (REQUIRED — no default)
#   S3_PREFIX         base key prefix (default: postgres)
#   AWS_PROFILE       aws CLI profile (default: doe-backup)
#   RETENTION_CLASS   one of daily|weekly|monthly (default: daily)
#   BACKUP_TIMEOUT    seconds before pg_dump is killed (default: 1800)
#   LOG_DIR           per-run logs (default: /var/log/doe)
#   LOCK_FILE         flock path (default: /var/lock/doe-backup.lock)
#   HC_PING_URL       healthchecks.io base URL (optional)
#   WEBHOOK_URL       Slack/Discord webhook for failures (optional)
#   MIN_FREE_MB       disk-space guard (default: 2048)
#
# FLAGS:
#   --dry-run                   preflight only; no dump, no upload
#   --retention daily|weekly|monthly
#   --verbose                   also turn on bash xtrace (passwords scrubbed)
# ========================================================================

set -Eeuo pipefail
IFS=$'\n\t'

# ---- DEFAULTS ----------------------------------------------------------
: "${REPO_DIR:=/home/deploy/agentic-doe}"
: "${S3_PREFIX:=postgres}"
: "${AWS_PROFILE:=doe-backup}"
: "${RETENTION_CLASS:=daily}"
: "${BACKUP_TIMEOUT:=1800}"
: "${LOG_DIR:=/var/log/doe}"
: "${LOCK_FILE:=/var/lock/doe-backup.lock}"
: "${MIN_FREE_MB:=2048}"
: "${HC_PING_URL:=}"
: "${WEBHOOK_URL:=}"

# ---- Parse flags -------------------------------------------------------
DRY_RUN=0
VERBOSE=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)   DRY_RUN=1 ;;
        --retention) RETENTION_CLASS="${2:?}"; shift ;;
        daily|weekly|monthly)
            # Allow positional retention class for the cron wrapper.
            RETENTION_CLASS="$1"
            ;;
        --verbose)   VERBOSE=1 ;;
        -h|--help)
            sed -n '2,80p' "$0"; exit 0 ;;
        *)
            echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
    shift
done

case "$RETENTION_CLASS" in
    daily|weekly|monthly) ;;
    *) echo "RETENTION_CLASS must be daily|weekly|monthly, got: $RETENTION_CLASS" >&2; exit 2 ;;
esac

# ---- Load env ----------------------------------------------------------
# /etc/default/doe-backup is the operator-owned override file.
if [[ -r /etc/default/doe-backup ]]; then
    # shellcheck disable=SC1091
    source /etc/default/doe-backup
fi
# Repo .env gives us POSTGRES_USER/DB/etc.
if [[ -r "$REPO_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$REPO_DIR/.env"
    set +a
fi

: "${POSTGRES_USER:?POSTGRES_USER not set (check $REPO_DIR/.env)}"
: "${POSTGRES_DB:?POSTGRES_DB not set (check $REPO_DIR/.env)}"
: "${S3_ENDPOINT_URL:?S3_ENDPOINT_URL is required (e.g. https://fsn1.your-objectstorage.com)}"
: "${S3_BUCKET:?S3_BUCKET is required}"

if [[ "$VERBOSE" == "1" ]]; then
    # xtrace with password scrub — prefix captures BASH_COMMAND before each line.
    PS4='+ [$(date -u +%H:%M:%S)] '
    set -x
fi

# ---- Paths / stamps ----------------------------------------------------
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
YEAR="${STAMP:0:4}"; MONTH="${STAMP:4:2}"; DAY="${STAMP:6:2}"
HOSTNAME_SHORT="$(hostname -s)"
GIT_SHA="$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || echo nogit)"
WORK_DIR="$(mktemp -d -t doe-backup-XXXXXX)"
DUMP_FILE="$WORK_DIR/${POSTGRES_DB}-$STAMP-$GIT_SHA.dump"
S3_KEY="$S3_PREFIX/$RETENTION_CLASS/$YEAR/$MONTH/$DAY/${POSTGRES_DB}-$STAMP-$GIT_SHA.dump"

mkdir -p "$LOG_DIR"
RUN_LOG="$LOG_DIR/backup-$STAMP.log"
: > "$RUN_LOG"

# ---- Logging helpers ---------------------------------------------------
log()  { printf '[%s] [%-5s] %s\n' "$(date -u +%H:%M:%S)" "$1" "${*:2}" | tee -a "$RUN_LOG"; }
step() { log STEP "$*"; }
ok()   { log OK    "$*"; }
warn() { log WARN  "$*"; }
die()  { log ERROR "$*"; exit 1; }

step "backup-postgres.sh starting"
log INFO "stamp=$STAMP retention=$RETENTION_CLASS host=$HOSTNAME_SHORT git=$GIT_SHA"
log INFO "s3_key=s3://$S3_BUCKET/$S3_KEY"
log INFO "endpoint=$S3_ENDPOINT_URL"
log INFO "log_file=$RUN_LOG"

# ---- Concurrency guard -------------------------------------------------
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    die "another backup is already running (lock=$LOCK_FILE); aborting"
fi

# ---- Trap-based completion / cleanup -----------------------------------
EVENT_ID=""
FINAL_STATUS="failed"
FINAL_ERROR=""
FINAL_PAYLOAD_MERGE_FILE=""

aws_do() {
    aws --profile "$AWS_PROFILE" --endpoint-url "$S3_ENDPOINT_URL" "$@"
}

hc_ping() {
    [[ -n "$HC_PING_URL" ]] || return 0
    local suffix="$1" body="${2:-}"
    # Fire-and-forget; never fail the backup because monitoring is down.
    curl -fsS -m 10 --retry 2 -X POST \
        --data-binary "$body" \
        "${HC_PING_URL%/}${suffix}" >/dev/null 2>&1 || true
}

webhook_fail() {
    [[ -n "$WEBHOOK_URL" ]] || return 0
    local payload
    payload=$(jq -nc \
        --arg id "$EVENT_ID" \
        --arg host "$HOSTNAME_SHORT" \
        --arg err "$FINAL_ERROR" \
        --arg key "$S3_KEY" \
        --arg log "$RUN_LOG" \
        '{event_type:"postgres_backup",status:"failed",event_id:$id,host:$host,
          error_message:$err,s3_key_attempted:$key,log_path:$log}')
    curl -fsS -m 10 --retry 2 -H 'content-type: application/json' \
        -d "$payload" "$WEBHOOK_URL" >/dev/null 2>&1 || true
}

close_admin_event_via_cli() {
    # Returns 0 on success, non-zero if the CLI path is unavailable.
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

close_admin_event_via_psql_fallback() {
    # Last-resort: write a failed row directly via psql inside the
    # postgres container. Only used if the app container / uv path is
    # broken at the moment of failure.
    [[ -n "$EVENT_ID" ]] || return 0
    ( cd "$REPO_DIR" && docker compose exec -T postgres \
        psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
            -v id="$EVENT_ID" -v err="$FINAL_ERROR" -v status="$FINAL_STATUS" \
            <<'SQL' >>"$RUN_LOG" 2>&1 || true
UPDATE admin_events
   SET status = :'status',
       error_message = NULLIF(:'err', ''),
       completed_at = now(),
       duration_ms = CASE
           WHEN started_at IS NOT NULL
             THEN (EXTRACT(EPOCH FROM (now() - started_at)) * 1000)::int
           ELSE NULL
       END
 WHERE id = :'id'::uuid;
SQL
    )
}

on_exit() {
    local rc=$?
    if [[ "$rc" -ne 0 ]]; then
        FINAL_STATUS="failed"
        if [[ -z "$FINAL_ERROR" ]]; then
            FINAL_ERROR="backup-postgres.sh exited with status $rc"
        fi
    fi

    if [[ -n "$EVENT_ID" ]]; then
        if ! close_admin_event_via_cli; then
            warn "CLI admin-event finish failed — falling back to psql"
            close_admin_event_via_psql_fallback
        fi
    fi

    if [[ "$FINAL_STATUS" == "success" ]]; then
        hc_ping "" "$(tail -n 50 "$RUN_LOG" 2>/dev/null || true)"
    else
        hc_ping "/fail" "$(tail -n 200 "$RUN_LOG" 2>/dev/null || true)"
        webhook_fail
    fi

    # Summary block (last lines cron captures).
    {
        echo "===== BACKUP SUMMARY ====="
        printf 'status:    %s\n' "${FINAL_STATUS^^}"
        printf 's3 key:    s3://%s/%s\n' "$S3_BUCKET" "$S3_KEY"
        printf 'event_id:  %s\n' "${EVENT_ID:-(not created)}"
        printf 'log file:  %s\n' "$RUN_LOG"
        if [[ -n "$FINAL_ERROR" ]]; then
            printf 'error:     %s\n' "$FINAL_ERROR"
        fi
        echo "=========================="
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
for bin in aws jq docker sha256sum flock stat curl; do
    command -v "$bin" >/dev/null 2>&1 || die "missing required tool: $bin"
done
docker compose version >/dev/null 2>&1 || die "docker compose v2 is required"
ok "tooling present"

step "preflight: S3 credentials + bucket reachability"
aws_do sts get-caller-identity >>"$RUN_LOG" 2>&1 \
    || die "aws sts get-caller-identity failed (profile=$AWS_PROFILE, endpoint=$S3_ENDPOINT_URL)"
aws_do s3api head-bucket --bucket "$S3_BUCKET" >>"$RUN_LOG" 2>&1 \
    || die "cannot head bucket $S3_BUCKET via $S3_ENDPOINT_URL"
ok "S3 credentials verified, bucket reachable"

if [[ "$DRY_RUN" == "0" ]]; then
    step "preflight: S3 write+delete probe"
    probe_key=".preflight/$HOSTNAME_SHORT-$STAMP"
    probe_local="$WORK_DIR/probe.txt"
    echo "ok $STAMP" > "$probe_local"
    aws_do s3 cp "$probe_local" "s3://$S3_BUCKET/$probe_key" --no-progress >>"$RUN_LOG" 2>&1 \
        || die "S3 put probe failed"
    aws_do s3 rm "s3://$S3_BUCKET/$probe_key" >>"$RUN_LOG" 2>&1 \
        || die "S3 delete probe failed"
    ok "S3 write+delete probe succeeded"
fi

step "preflight: postgres container health"
( cd "$REPO_DIR" && docker compose ps --status running postgres ) | grep -q postgres \
    || die "postgres container is not running"
( cd "$REPO_DIR" && docker compose exec -T postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" ) \
    >>"$RUN_LOG" 2>&1 \
    || die "pg_isready failed"
ok "postgres is ready"

step "preflight: disk space guard"
free_mb=$(df -Pm "$WORK_DIR" | awk 'NR==2{print $4}')
db_size_mb=$(( $(cd "$REPO_DIR" && docker compose exec -T postgres \
    psql -tAqX -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "SELECT pg_database_size('$POSTGRES_DB');" | tr -d '[:space:]') / 1024 / 1024 ))
need_mb=$(( db_size_mb * 3 / 2 ))
[[ "$need_mb" -lt "$MIN_FREE_MB" ]] && need_mb="$MIN_FREE_MB"
log INFO "free_mb=$free_mb  db_size_mb=$db_size_mb  need_mb=$need_mb"
(( free_mb >= need_mb )) || die "insufficient free space: $free_mb MiB < $need_mb MiB"
ok "disk space ok"

if [[ "$DRY_RUN" == "1" ]]; then
    step "dry-run: preflight complete, skipping dump + upload"
    FINAL_STATUS="success"
    FINAL_PAYLOAD_MERGE_FILE="$WORK_DIR/payload.json"
    jq -nc --arg mode "dry_run" '{mode:$mode}' > "$FINAL_PAYLOAD_MERGE_FILE"
    ok "dry-run complete"
    exit 0
fi

# ---- Record in_progress row in admin_events ----------------------------
step "recording admin_events.in_progress"
start_payload=$(jq -nc \
    --arg k "$S3_KEY" --arg b "$S3_BUCKET" --arg g "$GIT_SHA" \
    --arg r "$RETENTION_CLASS" --arg h "$HOSTNAME_SHORT" --arg log "$RUN_LOG" \
    --arg ep "$S3_ENDPOINT_URL" \
    '{s3_bucket:$b,s3_key:$k,s3_endpoint:$ep,retention_class:$r,
      git_sha:$g,hostname:$h,log_path:$log}')
EVENT_ID=$(
    cd "$REPO_DIR" && docker compose exec -T app \
        uv run python -m app.cli admin-event start \
            --type postgres_backup \
            --source "cron@$HOSTNAME_SHORT" \
            --payload-json "$start_payload" 2>>"$RUN_LOG" | tr -d '[:space:]'
)
if [[ -z "$EVENT_ID" ]]; then
    FINAL_ERROR="could not open admin_events in_progress row"
    die "$FINAL_ERROR"
fi
ok "admin_events id=$EVENT_ID"

# ---- Capture alembic head ---------------------------------------------
step "capturing alembic head"
ALEMBIC_HEAD=$(
    cd "$REPO_DIR" && docker compose exec -T app \
        uv run alembic current 2>>"$RUN_LOG" \
        | awk 'NF{print $1; exit}'
)
log INFO "alembic_head=$ALEMBIC_HEAD"

# ---- pg_dump -----------------------------------------------------------
step "pg_dump → $DUMP_FILE"
PG_DUMP_VERSION=$(
    cd "$REPO_DIR" && docker compose exec -T postgres pg_dump --version \
        | awk '{print $NF; exit}'
)
log INFO "pg_dump_version=$PG_DUMP_VERSION format=custom compress=9"
timeout "$BACKUP_TIMEOUT" bash -c '
    cd "$1" && docker compose exec -T postgres \
        pg_dump -U "$2" -d "$3" \
        --format=custom --compress=9 --no-owner --no-privileges
' _ "$REPO_DIR" "$POSTGRES_USER" "$POSTGRES_DB" > "$DUMP_FILE"
[[ -s "$DUMP_FILE" ]] || die "pg_dump produced an empty file"
ok "dump written ($(stat -c%s "$DUMP_FILE") bytes)"

# ---- Integrity ---------------------------------------------------------
step "computing sha256 + verifying dump structure"
SIZE_BYTES=$(stat -c%s "$DUMP_FILE")
SHA256=$(sha256sum "$DUMP_FILE" | awk '{print $1}')
log INFO "size_bytes=$SIZE_BYTES sha256=$SHA256"
# pg_restore --list parses the TOC; detects truncation.
( cd "$REPO_DIR" && docker compose exec -T postgres pg_restore --list ) \
    < "$DUMP_FILE" > /dev/null 2>>"$RUN_LOG" \
    || die "pg_restore --list could not parse the dump (truncated?)"
ok "dump structure verified"

# ---- Upload ------------------------------------------------------------
step "uploading to s3://$S3_BUCKET/$S3_KEY"
aws_do s3 cp "$DUMP_FILE" "s3://$S3_BUCKET/$S3_KEY" \
    --no-progress --sse AES256 \
    --expected-size "$SIZE_BYTES" \
    --metadata "sha256=$SHA256,alembic=$ALEMBIC_HEAD,git=$GIT_SHA,pg_format=custom,retention=$RETENTION_CLASS" \
    >>"$RUN_LOG" 2>&1 \
    || die "aws s3 cp failed"
ok "upload complete"

# ---- Verify upload -----------------------------------------------------
step "verifying remote object"
remote_json=$(aws_do s3api head-object --bucket "$S3_BUCKET" --key "$S3_KEY")
remote_size=$(echo "$remote_json" | jq -r '.ContentLength')
remote_sha=$(echo "$remote_json" | jq -r '.Metadata.sha256 // empty')
[[ "$remote_size" == "$SIZE_BYTES" ]] || die "size mismatch: local=$SIZE_BYTES remote=$remote_size"
[[ "$remote_sha"  == "$SHA256"    ]] || die "sha256 mismatch: local=$SHA256 remote=$remote_sha"
ok "remote object verified"

# ---- Mark success ------------------------------------------------------
FINAL_STATUS="success"
FINAL_PAYLOAD_MERGE_FILE="$WORK_DIR/payload.json"
jq -nc \
    --arg b "$S3_BUCKET" --arg k "$S3_KEY" --arg ep "$S3_ENDPOINT_URL" \
    --arg s "$SHA256" --arg h "$ALEMBIC_HEAD" --arg g "$GIT_SHA" \
    --arg r "$RETENTION_CLASS" --arg v "$PG_DUMP_VERSION" \
    --arg host "$HOSTNAME_SHORT" --arg log "$RUN_LOG" \
    --argjson sz "$SIZE_BYTES" \
    '{s3_bucket:$b,s3_key:$k,s3_endpoint:$ep,size_bytes:$sz,sha256:$s,
      alembic_head:$h,git_sha:$g,retention_class:$r,backup_format:"custom",
      compressed:true,pg_dump_version:$v,hostname:$host,log_path:$log}' \
    > "$FINAL_PAYLOAD_MERGE_FILE"
ok "backup succeeded"
