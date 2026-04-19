#!/usr/bin/env bash
# ========================================================================
# deploy-blue-green.sh — zero-downtime cutover between two backend
# containers (app-blue on :8000 / app-green on :8001) fronted by the
# host-level Caddy reverse proxy.
#
# The operator runbook lives in docs/deployment/vps-guide.md, section
# "Phase 13b: Zero-Downtime Redeploy". Quick summary:
#
#   1. Build + start the IDLE colour with the new image.
#   2. Wait for it to be healthy.
#   3. Run Alembic migrations (must be backwards-compatible with the
#      currently-live colour — see the expand/contract note in the
#      guide).
#   4. Rewrite /etc/caddy/active_backend.caddy to point at the new
#      colour's port and reload Caddy. Existing TCP connections on
#      the old colour stay open; new requests go to the new colour.
#   5. Sleep for the drain window so long-lived SSE streams on the
#      old colour can finish.
#   6. Stop the old colour container.
#
# Flags:
#   --drain-seconds N   drain window before stopping the old colour
#                       (default 120s). Set to 0 to skip.
#   --skip-build        reuse whatever image is already tagged for the
#                       idle colour (fast iteration; normally off)
#   --rollback          flip the currently-live colour back to the
#                       other one without rebuilding anything. Assumes
#                       the other colour container is still running
#                       (i.e. you are inside the drain window).
#   --force             skip the interactive "proceed?" gate (for CI)
# ========================================================================
set -euo pipefail

# ------------------------------------------------------------------ config

STATE_DIR="${STATE_DIR:-/var/lib/agentic-doe}"
STATE_FILE="${STATE_FILE:-$STATE_DIR/active-color}"
CADDY_SNIPPET="${CADDY_SNIPPET:-/etc/caddy/active_backend.caddy}"
CADDY_RELOAD_CMD="${CADDY_RELOAD_CMD:-sudo systemctl reload caddy}"
COMPOSE="${COMPOSE:-docker compose}"
HEALTH_URL_TEMPLATE="${HEALTH_URL_TEMPLATE:-http://127.0.0.1:%PORT%/api/v1/health}"
DRAIN_SECONDS="${DRAIN_SECONDS:-120}"

# Port assignment must match docker-compose.yml.
PORT_BLUE=8000
PORT_GREEN=8001

# --------------------------------------------------------------- arg parse

SKIP_BUILD=false
ROLLBACK=false
FORCE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --drain-seconds) DRAIN_SECONDS="$2"; shift 2 ;;
    --skip-build)    SKIP_BUILD=true; shift ;;
    --rollback)      ROLLBACK=true; shift ;;
    --force)         FORCE=true; shift ;;
    -h|--help)
      sed -n '2,35p' "$0"; exit 0 ;;
    *)
      echo "unknown flag: $1" >&2
      exit 2 ;;
  esac
done

# ------------------------------------------------------------------ helpers

log() { printf '[deploy-bg %s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
fail() { printf '[deploy-bg FAIL] %s\n' "$*" >&2; exit 1; }

read_active_color() {
  if [[ -f "$STATE_FILE" ]]; then
    cat "$STATE_FILE"
  else
    # First blue-green deploy on this host: default to "blue" being
    # the live colour so "next" = green.
    echo "blue"
  fi
}

write_active_color() {
  sudo mkdir -p "$STATE_DIR"
  printf '%s\n' "$1" | sudo tee "$STATE_FILE" >/dev/null
  sudo chmod 0644 "$STATE_FILE"
}

other_color() {
  case "$1" in
    blue)  echo "green" ;;
    green) echo "blue" ;;
    *)     fail "unknown colour: $1" ;;
  esac
}

port_for() {
  case "$1" in
    blue)  echo "$PORT_BLUE" ;;
    green) echo "$PORT_GREEN" ;;
    *)     fail "unknown colour: $1" ;;
  esac
}

wait_healthy() {
  local port="$1" timeout="${2:-90}" url
  url="${HEALTH_URL_TEMPLATE/%PORT%/$port}"
  log "waiting up to ${timeout}s for $url"
  local started_at=$SECONDS
  while (( SECONDS - started_at < timeout )); do
    if curl --silent --fail --max-time 3 "$url" >/dev/null; then
      log "healthy: $url"
      return 0
    fi
    sleep 2
  done
  fail "container never became healthy: $url"
}

write_caddy_snippet() {
  local port="$1"
  local tmp
  tmp="$(mktemp)"
  cat >"$tmp" <<EOF
# Managed by scripts/deploy-blue-green.sh — do not edit by hand.
# Last updated: $(date -u +%Y-%m-%dT%H:%M:%SZ)
reverse_proxy 127.0.0.1:${port}
EOF
  sudo install -m 0644 "$tmp" "$CADDY_SNIPPET"
  rm -f "$tmp"
}

reload_caddy() {
  log "validating Caddy config before reload"
  if command -v caddy >/dev/null 2>&1; then
    # Caddy ships with a validate subcommand; we only use it when the
    # binary is in PATH.
    sudo caddy validate --config /etc/caddy/Caddyfile >/dev/null || \
      fail "Caddy config invalid — aborting reload"
  fi
  log "reloading Caddy"
  eval "$CADDY_RELOAD_CMD"
}

ensure_legacy_app_stopped() {
  # If the non-blue-green ``app`` service is up, it occupies :8000 and
  # will conflict with app-blue. Stop without removing so the caller
  # can inspect its logs afterwards if needed.
  if $COMPOSE ps --services --status running 2>/dev/null | grep -Fxq "app"; then
    fail "Legacy 'app' service is still running on :8000. Stop it first with: $COMPOSE stop app && $COMPOSE rm -f app"
  fi
}

# ----------------------------------------------------------------- confirm

confirm() {
  $FORCE && return 0
  read -r -p "proceed? [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]] || fail "aborted"
}

# ------------------------------------------------------------------ main

current=$(read_active_color)
next=$(other_color "$current")

if $ROLLBACK; then
  log "rollback: flipping Caddy back from $current to $next (no rebuild)"
  confirm
  write_caddy_snippet "$(port_for "$next")"
  reload_caddy
  write_active_color "$next"
  log "rollback complete. traffic is now on $next (port $(port_for "$next"))."
  exit 0
fi

log "current active: $current ($(port_for "$current")) → next: $next ($(port_for "$next"))"
ensure_legacy_app_stopped
confirm

if ! $SKIP_BUILD; then
  log "building app-$next"
  $COMPOSE --profile "$next" build "app-$next"
fi

log "starting app-$next"
$COMPOSE --profile "$next" up -d "app-$next"

wait_healthy "$(port_for "$next")"

log "running Alembic migrations inside app-$next"
$COMPOSE --profile "$next" exec -T "app-$next" uv run alembic upgrade head

log "switching Caddy upstream to port $(port_for "$next")"
write_caddy_snippet "$(port_for "$next")"
reload_caddy
write_active_color "$next"

if (( DRAIN_SECONDS > 0 )); then
  log "draining $current for ${DRAIN_SECONDS}s so existing SSE streams finish"
  sleep "$DRAIN_SECONDS"
  log "stopping app-$current"
  $COMPOSE --profile "$current" stop "app-$current"
else
  log "drain window disabled (--drain-seconds=0); leaving app-$current running"
fi

log "deploy complete. active: $next ($(port_for "$next"))"
