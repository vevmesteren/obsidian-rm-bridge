// Pure helpers for Notice timeouts and modal bodies (Phase 5c).
//
// Extracted from main.ts so they are unit-testable in node:test without
// importing the `obsidian` module. main.ts composes these with the
// Obsidian `Notice`/`Modal` APIs.

import type { OrmbResult } from "./types.ts";

/**
 * Choose a Notice timeout (ms) for a CLI result. Success notices linger
 * 10s (long enough to read); error/warning notices linger 15s.
 */
export function noticeTimeout(res: OrmbResult): number {
  return res.ok ? 10_000 : 15_000;
}

/** Timeout for a generic warning/busy notice (no result object). */
export const NOTICE_WARN_TIMEOUT = 15_000;
/** Timeout for a generic success notice (no result object). */
export const NOTICE_OK_TIMEOUT = 10_000;

/**
 * Body text for the republish confirmation modal (AC-2). Shown when
 * `publish` returns `doc_exists`. The default publish still uses
 * `--on-exists fail`; the replace is explicit, modal-confirmed, and
 * preserves existing reMarkable annotations (content-only update).
 */
export function buildRepublishBody(fileBasename: string): string {
  return (
    `Document "${fileBasename}" already exists on reMarkable. ` +
    `Replace its content? Existing reMarkable annotations are preserved ` +
    `(content-only update via --on-exists content-only).`
  );
}
