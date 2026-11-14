import { test } from "node:test";
import assert from "node:assert/strict";
import { buildRepublishBody, noticeTimeout } from "../notice.ts";
import type { OrmbResult } from "../types.ts";

// ---------------------------------------------------------------------------
// noticeTimeout — Notice timeout selection (AC-1)
// ---------------------------------------------------------------------------

test("noticeTimeout: returns 10s (10000ms) for ok results", () => {
  const res: OrmbResult = { ok: true, code: "published", message: "ok", data: null };
  assert.equal(noticeTimeout(res), 10_000);
});

test("noticeTimeout: returns 15s (15000ms) for error results", () => {
  const res: OrmbResult = { ok: false, code: "doc_exists", message: "exists", data: null };
  assert.equal(noticeTimeout(res), 15_000);
});

test("noticeTimeout: 15s for cli_error", () => {
  const res: OrmbResult = { ok: false, code: "cli_error", message: "boom", data: null };
  assert.equal(noticeTimeout(res), 15_000);
});

// ---------------------------------------------------------------------------
// buildRepublishBody — republish modal body (AC-2)
// ---------------------------------------------------------------------------

test("buildRepublishBody: mentions the note name, replace, and preserved annotations", () => {
  const text = buildRepublishBody("My Note.md");
  assert.ok(text.includes("My Note.md"), "mentions the note name");
  assert.ok(/replace/i.test(text), "mentions replace");
  assert.ok(/annotation/i.test(text), "mentions annotations");
  assert.ok(/preserv/i.test(text), "mentions annotations being preserved");
});
