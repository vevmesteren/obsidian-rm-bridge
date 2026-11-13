import { test } from "node:test";
import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { winToWsl } from "../path-translate.ts";
import { WslAdapter } from "../wsl-adapter.ts";
import type { PlatformConfig } from "../types.ts";

// ---------------------------------------------------------------------------
// winToWsl — pure path translation (item 4)
// ---------------------------------------------------------------------------

test("winToWsl: normal drive path translates to /mnt/<drive>/...", () => {
  assert.equal(
    winToWsl("C:\\Users\\val\\Documents\\note.md", "/mnt"),
    "/mnt/c/Users/val/Documents/note.md",
  );
});

test("winToWsl: honours a custom automount root", () => {
  assert.equal(
    winToWsl("D:\\Vault\\note.md", "/mnt/wsl"),
    "/mnt/wsl/d/Vault/note.md",
  );
});

test("winToWsl: UNC paths are rejected", () => {
  assert.throws(
    () => winToWsl("\\\\server\\share\\file.md", "/mnt"),
    /UNC/i,
  );
});

test("winToWsl: control characters (NUL) are rejected", () => {
  assert.throws(
    () => winToWsl("C:\\Users\\note\x00.md", "/mnt"),
    /control/i,
  );
});

test("winToWsl: non-drive-letter paths are rejected", () => {
  assert.throws(
    () => winToWsl("Users\\note.md", "/mnt"),
    /Unsupported|drive/i,
  );
});

test("winToWsl: converts backslashes to forward slashes", () => {
  const out = winToWsl("E:\\a\\b\\c\\d.md", "/mnt");
  assert.equal(out, "/mnt/e/a/b/c/d.md");
  assert.ok(!out.includes("\\"), "no backslashes remain");
});

test("winToWsl: drive letter is lowercased", () => {
  assert.equal(
    winToWsl("Z:\\Folder\\note.md", "/mnt"),
    "/mnt/z/Folder/note.md",
  );
});

// ---------------------------------------------------------------------------
// WslAdapter spawn argv construction (item 3 / item 8)
// ---------------------------------------------------------------------------

const baseConfig: PlatformConfig = {
  launcher: "python -m obsidian_rm_bridge",
  distro: "Ubuntu",
  pythonBin: "/home/u/.venvs/ormb/bin/python",
  rmFolder: "/Obsidian",
  visionModel: "",
  automountRoot: "/mnt",
};

function makeFakeSpawn(): { spawn: any; recorded: () => any } {
  let recorded: any = null;
  const spawn = (cmd: string, args: string[], opts: any) => {
    recorded = { cmd, args, opts };
    const child: any = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    child.kill = () => true;
    // Emit a publish-success envelope asynchronously.
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

test("WslAdapter.spawn: uses absolute wsl.exe with --exec, shell false", async () => {
  const { spawn, recorded } = makeFakeSpawn();
  const adapter = new WslAdapter(baseConfig, null as any, spawn);
  await adapter.spawn(["doctor", "--json"]);
  const r = recorded();
  assert.ok(r.cmd.includes("System32"), "must use absolute path to wsl.exe");
  assert.ok(r.cmd.endsWith("wsl.exe"), "must end with wsl.exe");
  assert.ok(r.args.includes("--exec"), "must pass --exec");
  assert.equal(r.opts.shell, false, "shell must be false");
});

test("WslAdapter.spawn: windowsHide true and UTF-8 env set", async () => {
  const { spawn, recorded } = makeFakeSpawn();
  const adapter = new WslAdapter(baseConfig, null as any, spawn);
  await adapter.spawn(["doctor", "--json"]);
  const r = recorded();
  assert.equal(r.opts.windowsHide, true, "windowsHide must be true");
  assert.equal(r.opts.env.WSL_UTF8, "1", "WSL_UTF8=1 must be set");
  assert.equal(
    r.opts.env.PYTHONIOENCODING,
    "utf-8",
    "PYTHONIOENCODING=utf-8 must be set",
  );
});

test("WslAdapter.spawn: argv is wsl.exe [--distribution <d>] --exec python -m obsidian_rm_bridge ...args", async () => {
  const { spawn, recorded } = makeFakeSpawn();
  const adapter = new WslAdapter(baseConfig, null as any, spawn);
  await adapter.spawn(["publish", "note.md", "--json"]);
  const r = recorded();
  assert.ok(r.cmd.includes("System32"), "must use absolute path to wsl.exe");
  const args = r.args as string[];
  assert.ok(args.includes("--exec"));
  assert.ok(args.includes("-m"));
  assert.ok(args.includes("obsidian_rm_bridge"));
  assert.ok(args.includes("publish"));
  assert.ok(args.includes("note.md"));
  // No shell invocation anywhere.
  assert.ok(!args.includes("bash"));
  assert.ok(!args.includes("-c"));
  assert.ok(!args.some((a) => /cmd\.exe/.test(a)));
});

test("WslAdapter.spawn: passes --on-exists fail through to argv (R3)", async () => {
  const { spawn, recorded } = makeFakeSpawn();
  const adapter = new WslAdapter(baseConfig, null as any, spawn);
  await adapter.spawn(["publish", "note.md", "--vault", "/mnt/c/vault", "--on-exists", "fail", "--json"]);
  const r = recorded();
  const args = r.args as string[];
  assert.ok(args.includes("--on-exists"), "must pass --on-exists");
  const idx = args.indexOf("--on-exists");
  assert.equal(args[idx + 1], "fail", "--on-exists must be 'fail'");
});

test("WslAdapter.spawn: parses JSON envelope into OrmbResult", async () => {
  const { spawn } = makeFakeSpawn();
  const adapter = new WslAdapter(baseConfig, null as any, spawn);
  const res = await adapter.spawn(["publish", "note.md", "--json"]);
  assert.equal(res.ok, true);
  assert.equal(res.code, "published");
  assert.ok(res.data && "pages" in res.data, "publish data has pages");
  if (res.data && "pages" in res.data) {
    assert.equal(res.data.pages, 3);
  }
});

test("WslAdapter.spawn: parses JSON envelope even on non-zero exit", async () => {
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
      child.stderr.emit("data", Buffer.from("boom"));
      child.emit("close", 1);
    });
    return child;
  };
  const adapter = new WslAdapter(baseConfig, null as any, spawn);
  const res = await adapter.spawn(["publish", "note.md", "--json"]);
  assert.equal(res.ok, false);
  assert.equal(res.code, "doc_exists", "must parse JSON code on non-zero exit");
  assert.equal(res.message, "Document already exists");
});

test("WslAdapter.spawn: falls back to cli_error when no JSON on non-zero exit", async () => {
  const spawn = () => {
    const child: any = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    child.kill = () => true;
    queueMicrotask(() => {
      child.stderr.emit("data", Buffer.from("boom"));
      child.emit("close", 2);
    });
    return child;
  };
  const adapter = new WslAdapter(baseConfig, null as any, spawn);
  const res = await adapter.spawn(["doctor", "--json"]);
  assert.equal(res.ok, false);
  assert.equal(res.code, "cli_error");
});

test("WslAdapter.doctor: parses JSON even on non-zero exit (unhealthy)", async () => {
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
            version: "0.1.0",
            schema_version: 1,
            rmapi: { path: "", version: "", found: false },
            chromium: "missing",
            vault: "unknown",
            paired: false,
            key_present: false,
            errors: ["rmapi not found"],
          }),
        ),
      );
      child.emit("close", 1);
    });
    return child;
  };
  const adapter = new WslAdapter(baseConfig, null as any, spawn);
  const doc = await adapter.doctor();
  assert.equal(doc.ok, false);
  assert.equal(doc.rmapi.found, false);
  assert.equal(doc.errors[0], "rmapi not found");
});

test("WslAdapter.doctor: returns DoctorResult from doctor --json", async () => {
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
  const adapter = new WslAdapter(baseConfig, null as any, spawn);
  const doc = await adapter.doctor();
  assert.equal(doc.ok, true);
  assert.equal(doc.version, "0.1.0");
  assert.equal(doc.schema_version, 1);
  assert.equal(doc.paired, true);
  assert.equal(doc.rmapi.found, true);
});
