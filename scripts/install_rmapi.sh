#!/usr/bin/env bash
# install_rmapi.sh — download and install the ddvk/rmapi binary for the
# current platform (DC-2). Used by `ormb setup --rmapi`; also runnable
# standalone.
set -euo pipefail

SYSTEM="$(uname -s | tr '[:upper:]' '[:lower:]')"
MACHINE="$(uname -m | tr '[:upper:]' '[:lower:]')"

case "${SYSTEM}:${MACHINE}" in
  linux:aarch64|linux:arm64) ASSET="rmapi-linux-arm64.tar.gz" ;;
  linux:*)                   ASSET="rmapi-linux-amd64.tar.gz" ;;
  darwin:arm64)              ASSET="rmapi-macos-arm64.zip" ;;
  darwin:*)                  ASSET="rmapi-macos-intel.zip" ;;
  *) echo "Unsupported platform: ${SYSTEM} ${MACHINE}" >&2; exit 1 ;;
esac

URL="https://github.com/ddvk/rmapi/releases/latest/download/${ASSET}"
DEST="${HOME}/.local/bin"
mkdir -p "${DEST}"

echo "Downloading ${URL} ..."
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
curl -fsSL "${URL}" -o "${TMP}/${ASSET}"

# Handle both .tar.gz (Linux) and .zip (macOS) archives (Copilot #5).
case "${ASSET}" in
  *.tar.gz) tar -xzf "${TMP}/${ASSET}" -C "${TMP}" ;;
  *.zip)    unzip -o "${TMP}/${ASSET}" -d "${TMP}" ;;
esac

install -m 0755 "${TMP}/rmapi" "${DEST}/rmapi"
echo "Installed rmapi to ${DEST}/rmapi — ensure ${DEST} is on your PATH."
