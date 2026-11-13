import { test } from "node:test";
import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { WslAdapter } from "../wsl-adapter.ts";
import { buildPullArgs } from "../pull-args.ts";
import {
  applyMarkerBlock,
  buildConsentBody,
  buildMarkerBlock,
  stripExistingAnnotations,
} from "../marker-block.ts";
import type { OrmbPullData, PlatformConfig } from "../types.ts";

// ---------------------------------------------------------------------------
// buildPullArgs — argv contract for `ormb pull --emit json` (Phase 5b)
// ---------------------------------------------------------------------------

test("buildPullArgs: passes file basename (no .md) as the page_name positional", () => {
  const args = buildPullArgs(
    { path: "dir/My Note.md", basename: "My Note" },
    "/mnt/c/vault",
    "/Obsidian",
  );
  assert.equal(args[0], "pull");
  // page_name is a positional the CLI requires (cli.py:110,311) — must be
  // the basename WITHOUT .md, matching what publish sends (Path.stem).
  assert.equal(args[1], "My Note");
  assert.ok(!args[1].endsWith(".md"), "page_name must not include .md extension");
});

test("buildPullArgs: includes --emit json, --vault, --rm-folder, --json", () => {
  const args = buildPullArgs(
    { path: "note.md", basename: "note" },
    "/mnt/c/vault",
    "/Obsidian",
  );
  assert.ok(args.includes("--emit"));
  assert.equal(args[args.indexOf("--emit") + 1], "json");
  assert.ok(args.includes("--vault"));
  assert.equal(args[args.indexOf("--vault") + 1], "/mnt/c/vault");
  assert.ok(args.includes("--rm-folder"));
  assert.equal(args[args.indexOf("--rm-folder") + 1], "/Obsidian");
  assert.ok(args.includes("--json"));
});

test("buildPullArgs: does not pass --md (dead on the --emit json path)", () => {
  const args = buildPullArgs(
    { path: "note.md", basename: "note" },
    "/mnt/c/vault",
    "/Obsidian",
  );
  assert.ok(!args.includes("--md"), "--md is unused by retrieve_to_json");
});

// ---------------------------------------------------------------------------
// buildMarkerBlock — marker comment format (Phase 5b)
// ---------------------------------------------------------------------------

test("buildMarkerBlock: produces <!-- ormb:annotations doc=... rev=... -->", () => {
  const data: OrmbPullData = {
    sections: [],
    doc_id: "my-page",
    rev: "abc12345",
    total_pages: 3,
    annotated_pages: 0,
  };
  assert.equal(
    buildMarkerBlock(data),
    '<!-- ormb:annotations doc="my-page" rev="abc12345" -->',
  );
});

test("buildMarkerBlock: escapes nothing exotic — doc/rev are interpolated verbatim", () => {
  const data: OrmbPullData = {
    sections: [],
    doc_id: "notes/sub-page",
    rev: "deadbeef",
    total_pages: 1,
    annotated_pages: 0,
  };
  assert.equal(
    buildMarkerBlock(data),
    '<!-- ormb:annotations doc="notes/sub-page" rev="deadbeef" -->',
  );
});

// ---------------------------------------------------------------------------
// stripExistingAnnotations — remove marker + everything after it
// ---------------------------------------------------------------------------

test("stripExistingAnnotations: removes marker block and trailing sections", () => {
  const content =
    "# Original\n\n" +
    '<!-- ormb:annotations doc="x" rev="deadbeef" -->\n' +
    "**Page 1:**\n> scribble\n";
  assert.equal(stripExistingAnnotations(content), "# Original");
});

test("stripExistingAnnotations: leaves content with no marker unchanged", () => {
  const content = "# Just a note\n\nNo markers here.\n";
  assert.equal(stripExistingAnnotations(content), content);
});

test("stripExistingAnnotations: strips from the first marker to end of file", () => {
  const content =
    "Keep me\n\n" +
    '<!-- ormb:annotations doc="a" rev="11111111" -->\n' +
    "annot1\n" +
    '<!-- ormb:annotations doc="b" rev="22222222" -->\n' +
    "annot2\n";
  assert.equal(stripExistingAnnotations(content), "Keep me");
});

// ---------------------------------------------------------------------------
// applyMarkerBlock — replace, not duplicate (ARB R4)
// ---------------------------------------------------------------------------

test("applyMarkerBlock: appends marker + sections with page headers to clean content", () => {
  const content = "# Note";
  const data: OrmbPullData = {
    sections: [{ page: 1, text: "> first scribble" }],
    doc_id: "note",
    rev: "cafef00d",
    total_pages: 1,
    annotated_pages: 1,
  };
  const out = applyMarkerBlock(content, buildMarkerBlock(data), data);
  assert.equal(
    out,
    '# Note\n<!-- ormb:annotations doc="note" rev="cafef00d" -->\n## Page 1\n\n> first scribble\n',
  );
});

test("applyMarkerBlock: replaces existing marker + sections, does not duplicate", () => {
  const content =
    "# Note\n" +
    '<!-- ormb:annotations doc="note" rev="oldoldol" -->\n' +
    "## Page 1\n\n> old\n";
  const data: OrmbPullData = {
    sections: [{ page: 2, text: "> new" }],
    doc_id: "note",
    rev: "newnewne",
    total_pages: 2,
    annotated_pages: 1,
  };
  const out = applyMarkerBlock(content, buildMarkerBlock(data), data);
  assert.ok(out.includes('rev="newnewne"'), "new rev present");
  assert.ok(!out.includes("oldoldol"), "old rev gone");
  assert.ok(out.includes("> new"), "new section text present");
  assert.ok(!out.includes("> old"), "old section text gone");
  // Only one marker block.
  assert.equal(
    (out.match(/<!-- ormb:annotations/g) || []).length,
    1,
    "exactly one marker block",
  );
});

// ---------------------------------------------------------------------------
// buildMarkerBlock — sanitization (grok suggestion)
// ---------------------------------------------------------------------------

test("buildMarkerBlock: sanitizes quote and -- in doc_id/rev", () => {
  const data: OrmbPullData = {
    sections: [],
    doc_id: 'evil"-->',
    rev: 'bad-->',
    total_pages: 0,
    annotated_pages: 0,
  };
  const marker = buildMarkerBlock(data);
  // The marker template has 4 quotes (2 pairs for doc/rev). The
  // injected " is sanitized so no EXTRA quotes appear.
  const quoteCount = (marker.match(/"/g) || []).length;
  assert.equal(quoteCount, 4, "exactly 4 quotes (template pairs only)");
  assert.equal((marker.match(/-->/g) || []).length, 1, "exactly one --> (the close)");
});

// ---------------------------------------------------------------------------
// Empty pull protection (grok C1)
// ---------------------------------------------------------------------------

test("applyMarkerBlock: empty sections should not wipe existing content", () => {
  // This test documents the contract: the plugin's pullAnnotations
  // guards against empty pulls BEFORE calling applyMarkerBlock.
  // If sections is empty, applyMarkerBlock would still strip existing
  // annotations and write an empty block — so the plugin must check first.
  const content =
    "# Note\n" +
    '<!-- ormb:annotations doc="note" rev="oldoldol" -->\n' +
    "## Page 1\n\n> existing annotation\n";
  const data: OrmbPullData = {
    sections: [],
    doc_id: "note",
    rev: "00000000",
    total_pages: 5,
    annotated_pages: 0,
  };
  // The plugin checks annotated_pages === 0 and skips the write.
  // Document the contract: applyMarkerBlock with empty sections WOULD wipe.
  const out = applyMarkerBlock(content, buildMarkerBlock(data), data);
  assert.ok(!out.includes("existing annotation"), "empty apply wipes — plugin must guard");
});

// ---------------------------------------------------------------------------
// buildConsentBody — pull consent disclosure text
// ---------------------------------------------------------------------------

test("buildConsentBody: mentions file basename, model, and OpenRouter egress", () => {
  const text = buildConsentBody("My Note.md", "z-ai/glm-4.5v");
  assert.ok(text.includes("My Note.md"), "mentions file name");
  assert.ok(text.includes("z-ai/glm-4.5v"), "mentions model");
  assert.ok(/OpenRouter/i.test(text), "discloses OpenRouter egress");
});

test("buildConsentBody: falls back to CLI default model when blank", () => {
  const text = buildConsentBody("n.md", "");
  assert.ok(/CLI default/i.test(text), "notes CLI default");
});

// ---------------------------------------------------------------------------
// WslAdapter.spawn onStderr callback — best-effort status bar (Phase 5b)
// ---------------------------------------------------------------------------

const baseConfig: PlatformConfig = {
  launcher: "python -m obsidian_rm_bridge",
  distro: "Ubuntu",
  pythonBin: "/home/u/.venvs/ormb/bin/python",
  rmFolder: "/Obsidian",
  visionModel: "",
  automountRoot: "/mnt",
};

test("WslAdapter.spawn: onStderr fires once per stderr line", async () => {
  const spawn = () => {
    const child: any = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    child.kill = () => true;
    queueMicrotask(() => {
      child.stderr.emit("data", Buffer.from("Rendering page 1...\n"));
      child.stderr.emit("data", Buffer.from("Transcribing...\nDone\n"));
      child.stdout.emit(
        "data",
        Buffer.from(
          JSON.stringify({
            ok: true,
            code: "transcribed",
            message: "pulled",
            data: null,
          }),
        ),
      );
      child.emit("close", 0);
    });
    return child;
  };
  const lines: string[] = [];
  const adapter = new WslAdapter(baseConfig, null as any, spawn);
  const res = await adapter.spawn(["pull", "--emit", "json"], (line) =>
    lines.push(line),
  );
  assert.equal(res.ok, true);
  assert.equal(res.code, "transcribed");
  assert.deepEqual(lines, [
    "Rendering page 1...",
    "Transcribing...",
    "Done",
  ]);
});

test("WslAdapter.spawn: works without onStderr (back-compat)", async () => {
  const spawn = () => {
    const child: any = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    child.kill = () => true;
    queueMicrotask(() => {
      child.stderr.emit("data", Buffer.from("noise\n"));
      child.stdout.emit(
        "data",
        Buffer.from(
          JSON.stringify({ ok: true, code: "transcribed", message: "", data: null }),
        ),
      );
      child.emit("close", 0);
    });
    return child;
  };
  const adapter = new WslAdapter(baseConfig, null as any, spawn);
  const res = await adapter.spawn(["pull", "--emit", "json"]);
  assert.equal(res.ok, true);
});
