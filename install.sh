#!/usr/bin/env bash
# tokentelemetry — one-line installer.
#   curl -fsSL https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.sh | bash
set -euo pipefail

REPO_URL="https://github.com/VasiHemanth/tokentelemetry.git"
TARGET_DIR="${TOKENTELEMETRY_DIR:-tokentelemetry}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: $1 is required but not installed."; exit 1; }; }

need git
need node
need npm
command -v python3 >/dev/null 2>&1 || need python

# Clone if we're not already inside the repo
if [ ! -f "./bin/cli.js" ]; then
  if [ -d "$TARGET_DIR" ]; then
    # Re-running the installer over an existing clone updates it (previously it
    # silently relaunched stale code). --ff-only keeps it safe: if the checkout
    # has local changes or has diverged, skip rather than clobber, and tell the
    # user to pull manually.
    echo "→ updating existing clone at $TARGET_DIR"
    git -C "$TARGET_DIR" pull --ff-only \
      || echo "  (skipped auto-update: local changes or diverged history — run 'git pull' in $TARGET_DIR to update)"
  else
    echo "→ cloning $REPO_URL → $TARGET_DIR"
    git clone --depth 1 "$REPO_URL" "$TARGET_DIR"
  fi
  cd "$TARGET_DIR"
fi

echo "✓ TokenTelemetry ready in $(pwd)"
echo "  Start it again any time with:  cd \"$(pwd)\" && ./start.sh"
exec node bin/cli.js
