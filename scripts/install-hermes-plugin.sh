#!/usr/bin/env bash
# Symlink the TokenTelemetry plugin into ~/.hermes/plugins/ so Hermes Dashboard
# discovers it on next launch. Honors HERMES_HOME if set.
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$REPO_ROOT/plugin/hermes-dashboard"
DEST_DIR="$HERMES_HOME/plugins/tokentelemetry"
DEST_LINK="$DEST_DIR/dashboard"

if [[ ! -d "$SRC" ]]; then
  echo "✗ Plugin source not found at $SRC" >&2
  exit 1
fi

mkdir -p "$DEST_DIR"

# If destination already exists, back it up (skip if it's already our symlink).
if [[ -L "$DEST_LINK" ]]; then
  current_target="$(readlink "$DEST_LINK")"
  if [[ "$current_target" == "$SRC" ]]; then
    echo "✓ Already installed: $DEST_LINK → $SRC"
    exit 0
  fi
  rm "$DEST_LINK"
elif [[ -e "$DEST_LINK" ]]; then
  backup="$DEST_LINK.bak.$(date +%s)"
  mv "$DEST_LINK" "$backup"
  echo "ℹ Backed up existing $DEST_LINK → $backup"
fi

ln -s "$SRC" "$DEST_LINK"
echo "✓ Installed: $DEST_LINK → $SRC"
echo ""
echo "Next steps:"
echo "  1. Start (or restart) the Hermes Dashboard:"
echo "       hermes dashboard"
echo "  2. Open http://127.0.0.1:9119 and click TokenTelemetry in the sidebar."
