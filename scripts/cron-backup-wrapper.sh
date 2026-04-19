#!/usr/bin/env bash
# ========================================================================
# cron-backup-wrapper.sh — thin shim cron invokes instead of
# backup-postgres.sh directly.
#
# Why a wrapper:
#   - cron's default PATH is painfully short; we explicitly export one.
#   - sources /etc/default/doe-backup so S3_ENDPOINT_URL, S3_BUCKET,
#     etc. are present even when cron strips the environment.
#   - uses `chronic` (from moreutils) so cron MAILTO stays quiet on
#     success and only emails the combined stdout+stderr on failure.
#
# Called as:
#   cron-backup-wrapper.sh [daily|weekly|monthly]
# ========================================================================

set -Eeuo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

RETENTION="${1:-daily}"

if [[ -r /etc/default/doe-backup ]]; then
    # shellcheck disable=SC1091
    source /etc/default/doe-backup
fi

: "${REPO_DIR:=/home/deploy/agentic-doe}"

cd "$REPO_DIR"

if command -v chronic >/dev/null 2>&1; then
    # chronic swallows stdout+stderr on success; re-emits both on failure.
    exec chronic "$REPO_DIR/scripts/backup-postgres.sh" --retention "$RETENTION"
else
    # Fallback: always show the last 80 log lines on failure.
    if ! "$REPO_DIR/scripts/backup-postgres.sh" --retention "$RETENTION"; then
        rc=$?
        latest_log=$(find "${LOG_DIR:-/var/log/doe}" -maxdepth 1 -name 'backup-*.log' \
                        -type f -printf '%T@ %p\n' 2>/dev/null \
                      | sort -nr | awk 'NR==1{print $2}')
        if [[ -n "$latest_log" ]]; then
            echo "------ last 80 lines of $latest_log ------" >&2
            tail -n 80 "$latest_log" >&2
        fi
        exit "$rc"
    fi
fi
