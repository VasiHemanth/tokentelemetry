#!/usr/bin/env bash
# Sync the canonical plugin source (plugin/hermes-dashboard/) into the
# standalone publishing repo (tokentelemetry-hermes-plugin), bump the
# version, commit, tag, and push.
#
# Prerequisites:
#   1. The standalone repo exists on GitHub. Create it once:
#        gh repo create VasiHemanth/tokentelemetry-hermes-plugin \
#          --public --license MIT \
#          --description "TokenTelemetry launcher for Hermes Dashboard"
#   2. You have push access to that repo.
#
# Usage:
#   ./scripts/publish-plugin.sh              # sync HEAD, no tag
#   ./scripts/publish-plugin.sh 0.2.0        # also bump version and tag v0.2.0
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_PLUGIN="$REPO_ROOT/plugin/hermes-dashboard"
TEMPLATE="$REPO_ROOT/scripts/publish-plugin-template"
PUBLISH_REPO="${PUBLISH_REPO:-git@github.com:VasiHemanth/tokentelemetry-hermes-plugin.git}"
NEW_VERSION="${1:-}"

if [[ ! -d "$SRC_PLUGIN" ]]; then
  echo "✗ Canonical plugin source not found: $SRC_PLUGIN" >&2
  exit 1
fi
if [[ ! -d "$TEMPLATE" ]]; then
  echo "✗ Publishing template missing: $TEMPLATE" >&2
  exit 1
fi

# Resolve the current commit so we can record provenance in the commit msg.
UPSTREAM_SHA="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "→ Cloning publishing repo to temp dir…"
git clone "$PUBLISH_REPO" "$TMP/repo"
cd "$TMP/repo"

# Wipe everything except .git so a removal upstream propagates.
find . -mindepth 1 -maxdepth 1 -not -name ".git" -exec rm -rf {} +

# Copy template scaffolding (plugin.yaml, README, LICENSE, .gitignore).
cp -a "$TEMPLATE/." .

# Copy the dashboard payload from the canonical source. The canonical layout
# (plugin/hermes-dashboard/) has manifest.json + dist/ at the root, but
# Hermes expects them under dashboard/ in the installed plugin tree, so we
# nest them here.
mkdir -p dashboard
cp -a "$SRC_PLUGIN/manifest.json" dashboard/manifest.json
cp -a "$SRC_PLUGIN/dist" dashboard/dist

# If a new version was supplied, bump plugin.yaml.
if [[ -n "$NEW_VERSION" ]]; then
  sed -i.bak -E "s/^version:.*/version: $NEW_VERSION/" plugin.yaml
  rm -f plugin.yaml.bak
  echo "→ Bumped plugin.yaml version → $NEW_VERSION"
fi

CURRENT_VERSION="$(awk '/^version:/ {print $2}' plugin.yaml)"

git add -A
if git diff --cached --quiet; then
  echo "✓ Nothing to publish — repo already in sync with $UPSTREAM_SHA."
  exit 0
fi

COMMIT_MSG="release: sync from tokentelemetry@$UPSTREAM_SHA"
[[ -n "$NEW_VERSION" ]] && COMMIT_MSG="$COMMIT_MSG (v$NEW_VERSION)"

git commit -m "$COMMIT_MSG"

if [[ -n "$NEW_VERSION" ]]; then
  git tag -a "v$NEW_VERSION" -m "v$NEW_VERSION"
fi

echo "→ Pushing to ${PUBLISH_REPO}…"
git push origin HEAD
[[ -n "$NEW_VERSION" ]] && git push origin "v$NEW_VERSION"

echo ""
echo "✓ Published version $CURRENT_VERSION from tokentelemetry@$UPSTREAM_SHA"
echo "  Install: hermes plugins install VasiHemanth/tokentelemetry-hermes-plugin"
