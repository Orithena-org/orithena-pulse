#!/usr/bin/env bash
# Wrapper script for launchd — loads .env, runs the Pulse pipeline,
# then commits and pushes site output so GitHub Pages deploys automatically.
set -euo pipefail

PULSE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CORE_ROOT="$(cd "$PULSE_ROOT/../orithena-org/infrastructure" && pwd)"

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
python3 -u -m content.pipeline --domain pulse

# --- Deploy: commit and push site output if changed ---
cd "$PULSE_ROOT"

# Ensure we're on main — if a Scout branch was left checked out, commits
# would go to the wrong branch and the push would silently push stale data.
current_branch=$(git rev-parse --abbrev-ref HEAD)
if [[ "$current_branch" != "main" ]]; then
    echo "[deploy] WARNING: was on branch '$current_branch', switching to main"
    git checkout main
    git pull origin main
fi

if ! git diff --quiet output/site/ 2>/dev/null || [ -n "$(git ls-files --others --exclude-standard output/site/)" ]; then
    git add output/site/
    git commit -m "chore(site): update generated site output $(date +%Y-%m-%d)"
    git push origin main
    echo "[deploy] Site output committed and pushed."
else
    echo "[deploy] No site changes to commit."
fi
