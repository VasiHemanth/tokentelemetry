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

# Absolute path to the checkout. The shim below points at this exact location,
# so it keeps working after the installer's shell exits and from any directory.
CHECKOUT_DIR="$(pwd)"

# Install a ~/.local/bin/tokentelemetry shim so the command resolves from any
# directory. A shim rather than npm link, because npm's global dir is
# Node-version-specific under nvm and a user who switches Node versions would
# silently lose the command. Idempotent: only rewritten when missing or
# pointing at a different checkout.
SHIM_DIR="${HOME}/.local/bin"
SHIM_PATH="${SHIM_DIR}/tokentelemetry"
if [ ! -f "$SHIM_PATH" ] || ! grep -Fq "$CHECKOUT_DIR" "$SHIM_PATH" >/dev/null 2>&1; then
  mkdir -p "$SHIM_DIR"
  cat > "$SHIM_PATH.tmp" <<EOF
#!/usr/bin/env bash
exec node "$CHECKOUT_DIR/bin/cli.js" "\$@"
EOF
  chmod +x "$SHIM_PATH.tmp"
  mv "$SHIM_PATH.tmp" "$SHIM_PATH"
fi

case ":$PATH:" in
  *":$SHIM_DIR:"*) ;;
  *) echo "⚠  ~/.local/bin is not on your PATH. Add it to run 'tokentelemetry' from any directory:"
     # The right rc file depends on the login shell: bash reads ~/.bashrc, zsh
     # (macOS default since Catalina) reads ~/.zshrc.
     case "${SHELL:-}" in
       */zsh|zsh)
         echo "    echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc"
         echo "    source ~/.zshrc"
         ;;
       */bash|bash)
         echo "    echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
         echo "    source ~/.bashrc"
         ;;
       *)
         echo "    Add \$HOME/.local/bin to your shell's startup file (~/.bashrc or ~/.zshrc), then reload it."
         ;;
     esac ;;
esac

echo "✓ TokenTelemetry ready in $(pwd)"
echo "  Start it again any time with:  cd \"$(pwd)\" && ./start.sh"
echo "  ... or from anywhere with:     tokentelemetry"
exec node bin/cli.js
