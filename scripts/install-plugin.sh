#!/usr/bin/env bash
# install-plugin.sh — build and install the Obsidian plugin into a vault.
#
# Usage:
#   ./scripts/install-plugin.sh <vault-path>
#   ./scripts/install-plugin.sh <vault-path> --watch    # rebuild on change
#
# Detects the platform and copies main.js + manifest.json to:
#   <vault>/.obsidian/plugins/obsidian-rm-bridge/
#
# On T-WSL, the vault path is a Windows path (C:\dev\veviki) or a WSL path
# (/mnt/c/dev/veviki). Both are handled.
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <vault-path>" >&2
  echo "  e.g. $0 /mnt/c/dev/veviki" >&2
  echo "  e.g. $0 'C:\dev\veviki'" >&2
  exit 1
fi

VAULT_RAW="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PLUGIN_DIR="${REPO_ROOT}/plugin"

# --- Resolve vault path -------------------------------------------------

# If it's a Windows-style path (C:\...), convert to WSL path if we're in WSL.
if [[ "${VAULT_RAW}" =~ ^([A-Za-z]):[\\\\/](.*) ]]; then
  if [ -d /mnt ]; then
    DRIVE=$(echo "${BASH_REMATCH[1]}" | tr '[:upper:]' '[:lower:]')
    REST="${BASH_REMATCH[2]//\\//}"
    VAULT="/mnt/${DRIVE}/${REST}"
  else
    # Native Windows (Git Bash) — keep as-is, use forward slashes
    VAULT="${VAULT_RAW//\\//}"
  fi
else
  VAULT="${VAULT_RAW}"
fi

if [ ! -d "${VAULT}" ]; then
  echo "Error: vault path not found: ${VAULT}" >&2
  echo "  (resolved from: ${VAULT_RAW})" >&2
  exit 1
fi

VAULT_PLUGINS="${VAULT}/.obsidian/plugins/obsidian-rm-bridge"

# --- Build --------------------------------------------------------------

echo "Building plugin..."
cd "${PLUGIN_DIR}"
if [ ! -d node_modules ]; then
  echo "  Installing dependencies..."
  npm install
fi
npm run build

if [ ! -f main.js ]; then
  echo "Error: build did not produce main.js" >&2
  exit 1
fi
if [ ! -f manifest.json ]; then
  echo "Error: manifest.json not found" >&2
  exit 1
fi

# --- Install ------------------------------------------------------------

echo "Installing to: ${VAULT_PLUGINS}"
mkdir -p "${VAULT_PLUGINS}"
cp main.js "${VAULT_PLUGINS}/"
cp manifest.json "${VAULT_PLUGINS}/"

# Copy styles.css if it exists
if [ -f styles.css ]; then
  cp styles.css "${VAULT_PLUGINS}/"
fi

echo ""
echo "✓ Plugin installed."
echo "  1. Open Obsidian → Settings → Community plugins"
echo "  2. Enable 'Obsidian reMarkable Bridge'"
echo "  3. Configure Python binary in the plugin settings tab"
echo ""
echo "  Vault: ${VAULT}"
echo "  Plugin: ${VAULT_PLUGINS}"