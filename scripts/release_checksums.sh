#!/usr/bin/env bash
# release_checksums.sh — generate a SHA256SUMS file for release artifacts.
#
# Phase 5c AC-6c: supply-chain hardening. Run this against a directory of
# release artifacts (e.g. the packaged plugin zip, PDFs, etc.) to produce
# a `SHA256SUMS` file consumers can verify with `sha256sum -c SHA256SUMS`.
#
# Usage:
#   scripts/release_checksums.sh [artifact_dir]
#
# Defaults to the current directory. Writes SHA256SUMS into that directory.
set -euo pipefail

DIR="${1:-.}"
if [ ! -d "${DIR}" ]; then
  echo "Error: '${DIR}' is not a directory" >&2
  exit 1
fi

OUT="${DIR}/SHA256SUMS"

# Generate sha256 lines for every regular file in the dir (excluding the
# checksum file itself if it already exists). Relative paths so the file is
# portable when distributed alongside the artifacts.
{
  if [ -f "${OUT}" ]; then
    find "${DIR}" -type f ! -name SHA256SUMS -printf '%P\n' | while read -r f; do
      sha256sum "${DIR}/${f}" | sed "s|${DIR}/||"
    done
  else
    find "${DIR}" -type f -printf '%P\n' | while read -r f; do
      sha256sum "${DIR}/${f}" | sed "s|${DIR}/||"
    done
  fi
} > "${OUT}"

echo "Wrote ${OUT}"
cat "${OUT}"
