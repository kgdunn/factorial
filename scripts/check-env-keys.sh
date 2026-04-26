#!/usr/bin/env sh
# Verifies that every key defined in .env.example is also present in .env.
#
# Presence-only check: values are NOT compared. The intent is to catch the
# "my .env was copied from a stale template" footgun before a deploy gets
# far enough to fail in confusing ways (a missing key turns into a
# pydantic validation error, a 500 on first request, etc.). Operators
# control values; this script only enforces the key set.
#
# Exits 0 if every key in .env.example also appears in .env.
# Exits 1 with the list of missing keys otherwise.
#
# Invoked from `make deploy-preflight`. Safe to run standalone too.

set -eu

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXAMPLE="${REPO_ROOT}/.env.example"
ENV_FILE="${REPO_ROOT}/.env"

if [ ! -f "$EXAMPLE" ]; then
    echo "ERROR: $EXAMPLE not found." >&2
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: $ENV_FILE not found. Run: cp .env.example .env and configure it." >&2
    exit 1
fi

# Pull KEY out of "KEY=value" lines. Anchored on a letter/underscore so
# comments (# ...) and blank lines are skipped automatically. cut -d= -f1
# stops at the first '=' so values containing '=' don't confuse us.
example_keys=$(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$EXAMPLE" | cut -d= -f1 | sort -u)

missing=""
for key in $example_keys; do
    # Anchor on both sides so FOO does not match FOOBAR.
    if ! grep -qE "^${key}=" "$ENV_FILE"; then
        if [ -z "$missing" ]; then
            missing="$key"
        else
            missing="$missing
$key"
        fi
    fi
done

if [ -n "$missing" ]; then
    {
        echo "ERROR: .env is missing keys defined in .env.example:"
        printf '%s\n' "$missing" | sed 's/^/  - /'
        echo ""
        echo "Copy the missing entries from .env.example into .env and re-run."
    } >&2
    exit 1
fi
