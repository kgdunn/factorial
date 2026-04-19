#!/usr/bin/env bash
# ========================================================================
# prune-old-run-logs.sh — remove backup/restore/drill run logs older
# than PRUNE_DAYS from $LOG_DIR. Safety net in case logrotate is not
# installed. logrotate (deploy/logrotate/doe-backup) is the primary
# mechanism — this script is just belt-and-braces.
#
# Usage:
#   PRUNE_DAYS=60 ./scripts/prune-old-run-logs.sh
# ========================================================================

set -Eeuo pipefail

: "${LOG_DIR:=/var/log/doe}"
: "${PRUNE_DAYS:=60}"

[[ -d "$LOG_DIR" ]] || { echo "LOG_DIR=$LOG_DIR does not exist"; exit 0; }

find "$LOG_DIR" -maxdepth 1 -type f \
    \( -name 'backup-*.log'   -o -name 'backup-*.log.gz' \
    -o -name 'restore-*.log'  -o -name 'restore-*.log.gz' \
    -o -name 'drill-*.log'    -o -name 'drill-*.log.gz' \) \
    -mtime +"$PRUNE_DAYS" \
    -print -delete
