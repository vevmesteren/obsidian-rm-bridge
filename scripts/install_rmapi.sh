#!/usr/bin/env bash
# install_rmapi.sh — download and install the ddvk/rmapi binary for the
# # current platform (DC-2). Used by `ormb setup --rmapi`; also runnable
# standalone.
#
# Phase 5c AC-6: the rmapi release is PINNED to a specific version and the
# downloaded archive is sha256-verified before extraction (supply-chain
# hardening). Bump RMAPI_VERSION and the matching sha256 below together.
set -euo pipefail

RMAPI_VERSION="v0.0.35"

SYSTEM="$(uname -s | tr '[:upper:]'[:lower:]')"
MACHINE="$(uname -m | tr '[:upper:]'[:lower:]')"

case "${SYSTEM}:${MACHINE}" in
  linux:aarch64|linux:arm64) ASSET="rmapi-linux-arm64.tar.gz"
                             SHA256="645c170d8119b4dcb652cf79612e362fcb032dc0e5869ff520eec1324da39637" ;;
  linux:*)                   ASSET="rmapi-linux-amd64.tar.gz"
                             SHA256="117616151d11937446ead6972b0934f97155443087f8406141db38fd1ac8fb25" ;;
  darwin:arm64)              ASSET="rmapi-macos-arm64.zip"
                             SHA256="fb55b6c782b83dc0ccbb236359d738727c4c600378feae920fcab505862f624a" ;;
  darwin:*)                  ASSET="rmapi-macos-intel.zip"
                             SHA256="1afc2c4d73ddde60e22e0ff8d2bc737450dfcaeaa723eb6a3b863ac96cb2102c" ;;
  *) echo "Unsupported platform: ${SYSTEM} ${MACHINE}" >&2; exit 1 ;;
esac

URL="https://github.com/ddvk/rmapi/releases/download/${RMAPI_VERSION}/${ASSET}"
DEST="${HOME}/.local/bin"
mkdir -p "${DEST}"

echo "Downloading ${URL} ..."
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
curl -fsSL "${URL}" -o "${TMP}/${ASSET}"

# Verify sha256 before extracting (Phase 5c AC-6).
ACTUAL="$(sha256sum "${TMP}/${ASSET}" | awk '{print $1}')"
if [ "${ACTUAL}" != "${SHA256}" ]; then
  echo "sha256 mismatch for ${ASSET}: expected ${SHA256}, got ${ACTUAL}" >&2
  echo "Refusing to install (possible tampering or wrong release)." >&2
  exit 1
fi
echo "sha256 verified: ${ACTUAL}"

# Handle both .tar.gz (Linux) and .zip (macOS) archives (Copilot #5).
case "${ASSET}" in
  *.tar.gz) tar -xzf "${TMP}/${ASSET}" -C "${TMP}" ;;
  *.zip)    unzip -o "${TMP}/${ASSET}" -d "${TMP}" ;;
esac

install -m 0755 "${TMP}/rmapi" "${DEST}/rmapi"
echo "Installed rmapi ${RMAPI_VERSION} to ${DEST}/rmapi — ensure ${DEST} is on your PATH."
