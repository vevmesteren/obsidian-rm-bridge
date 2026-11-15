import { test } from "node:test";
import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { NativeAdapter } from "../native-adapter.ts";
import type { PlatformConfig } from "../types.ts";

const baseConfig: PlatformConfig = {
  launcher: "python -m obsidian_rm_bridge",
  distro: "",
  pythonBin: "/usr/bin/python3",
  rmFolder: "/Obsidian",
  visionModel: "",
  automountRoot: "/mnt",
  topology: "linux",
};

function makeFakeSpawn(): { spawn: any; recorded: () => any } {
  let recorded: any = null;
  const spawn = (cmd: string, args: string[], opts: any) => {
    recorded = { cmd, args, opts };
    const child: any = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    child.kill = () => true;
    queueMicrotask(() => {
      child.stdout.emit(
        "data",
        Buffer.from(
          JSON.stringify({
            ok: true,
            code: "published",
            message: "Published 'note' to /Obsidian",
            data: { name: "note", folder: "Obsidian", dest: "/path", pages: 3 },
          }),
        ),
      );
      child.emit("close", 0);
    });
    return child;
  };
  return { spawn, recorded: () => recorded };
}

test("NativeAdapter.spawn: spawns config.pythonBin with shell false", async () => {
  const { spawn, recorded } = makeFakeSpawn();
  const adapter = new NativeAdapter(baseConfig, null as any, spawn);
  await adapter.spawn(["publish", "note.md", "--json"]);
  const r = recorded();
  assert.equal(r.cmd, "/usr/bin/python3", "must spawn the configured pythonBin");
  assert.equal(r.opts.shell, false, "shell must be false");
  assert.equal(r.opts.windowsHide, true, "windowsHide must be true");
});

test("NativeAdapter.spawn: argv is pythonBin -m obsidian_rm_bridge ...args (no wsl.exe, no --exec)", async () => {
  const { spawn, recorded } = makeFakeSpawn();
  const adapter = new NativeAdapter(baseConfig, null as any, spawn);
  await adapter.spawn(["publish", "note.md", "--json"]);
  const r = recorded();
  const args = r.args as string[];
  assert.equal(args[0], "-m", "first arg is -m");
  assert.equal(args[1], "obsidian_rm_bridge", "second arg is the module");
  assert.ok(args.includes("publish"), "passes publish through");
  assert.ok(args.includes("note.md"), "passes positional through");
  // No WSL trappings.
  assert.ok(!r.cmd.includes("wsl.exe"), "must not use wsl.exe");
  assert.ok(!args.includes("--exec"), "must not pass --exec");
  assert.ok(!args.includes("--distribution"), "must not pass --distribution");
  // No shell invocation anywhere.
  assert.ok(!args.includes("bash"));
  assert.ok(!args.includes("-c"));
  assert.ok(!args.some((a: string) => /cmd\.exe/.test(a)));
});

test("NativeAdapter.spawn: sets NO_COLOR and PYTHONIOENCODING env", async () => {
  const { spawn, recorded } = makeFakeSpawn();
  const adapter = new NativeAdapter(baseConfig, null as any, spawn);
  await adapter.spawn(["doctor", "--json"]);
  const r = recorded();
  assert.equal(r.opts.env.NO_COLOR, "1", "NO_COLOR=1");
  assert.equal(r.opts.env.PYTHONIOENCODING, "utf-8", "PYTHONIOENCODING=utf-8");
});

test("NativeAdapter.spawn: injects ORB_VISION_MODEL when visionModel set", async () => {
  const cfg: PlatformConfig = { ...baseConfig, visionModel: "z-ai/glm-4.5v" };
  const { spawn, recorded } = makeFakeSpawn();
  const adapter = new NativeAdapter(cfg, null as any, spawn);
  await adapter.spawn(["pull", "--emit", "json"]);
  const r = recorded();
  assert.equal(r.opts.env.ORB_VISION_MODEL, "z-ai/glm-4.5v", "vision model injected");
});

test("NativeAdapter.translateVaultRoot: returns the path unchanged", () => {
  const adapter = new NativeAdapter(baseConfig, null as any);
  assert.equal(adapter.translateVaultRoot("/home/u/vault"), "/home/u/vault");
  assert.equal(adapter.translateVaultRoot("C:\\Users\\val"), "C:\\Users\\val");
});

test("NativeAdapter.spawn: parses JSON envelope into OrmbResult", async () => {
  const { spawn } = makeFakeSpawn();
  const adapter = new NativeAdapter(baseConfig, null as any, spawn);
  const res = await adapter.spawn(["publish", "note.md", "--json"]);
  assert.equal(res.ok, true);
  assert.equal(res.code, "published");
  assert.ok(res.data && "pages" in res.data, "publish data has pages");
});

test("NativeAdapter.spawn: parses JSON envelope even on non-zero exit", async () => {
  const spawn = () => {
    const child: any = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    child.kill = () => true;
    queueMicrotask(() => {
      child.stdout.emit(
        "data",
        Buffer.from(
          JSON.stringify({
            ok: false,
            code: "doc_exists",
            message: "Document already exists",
            data: null,
          }),
        ),
      );
      child.emit("close", 1);
    });
    return child;
  };
  const adapter = new NativeAdapter(baseConfig, null as any, spawn);
  const res = await adapter.spawn(["publish", "note.md", "--json"]);
  assert.equal(res.ok, false);
  assert.equal(res.code, "doc_exists", "must parse JSON code on non-zero exit");
});

test("NativeAdapter.spawn: onStderr fires once per stderr line", async () => {
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
        Buffer.from(JSON.stringify({ ok: true, code: "transcribed", message: "", data: null })),
      );
      child.emit("close", 0);
    });
    return child;
  };
  const lines: string[] = [];
  const adapter = new NativeAdapter(baseConfig, null as any, spawn);
  await adapter.spawn(["pull", "--emit", "json"], (line) => lines.push(line));
  assert.deepEqual(lines, ["Rendering page 1...", "Transcribing...", "Done"]);
});

test("NativeAdapter.doctor: parses JSON from doctor --json", async () => {
  const spawn = () => {
    const child: any = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    child.kill = () => true;
    queueMicrotask(() => {
      child.stdout.emit(
        "data",
        Buffer.from(
          JSON.stringify({
            ok: true,
            version: "0.1.0",
            schema_version: 1,
            rmapi: { path: "/usr/bin/rmapi", version: "0.1.0", found: true },
            chromium: "ok",
            vault: "reachable",
            paired: true,
            key_present: true,
            errors: [],
          }),
        ),
      );
      child.emit("close", 0);
    });
    return child;
  };
  const adapter = new NativeAdapter(baseConfig, null as any, spawn);
  const doc = await adapter.doctor();
  assert.equal(doc.ok, true);
  assert.equal(doc.version, "0.1.0");
  assert.equal(doc.paired, true);
  assert.equal(doc.rmapi.found, true);
});
