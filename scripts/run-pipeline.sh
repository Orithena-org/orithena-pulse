#!/usr/bin/env bash
# Wrapper script for launchd — loads .env and runs the Pulse pipeline.
set -euo pipefail

PULSE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CORE_ROOT="$(cd "$PULSE_ROOT/../orithena-core" && pwd)"

# launchd starts with a minimal PATH — add common tool locations
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"

# Source .env (contains DISCORD_WEBHOOK_PULSE and API keys)
if [[ -f "$CORE_ROOT/.env" ]]; then
    set -a
    source "$CORE_ROOT/.env"
    set +a
fi

ORG_ROOT="$(cd "$PULSE_ROOT/../orithena-org" && pwd)"
cd "$ORG_ROOT"
exec python3 -u -m content.pipeline --domain pulse
