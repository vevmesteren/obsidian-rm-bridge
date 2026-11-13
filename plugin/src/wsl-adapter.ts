// ExecutionAdapter for the primary topology (T-WSL): Obsidian on Windows,
// ormb CLI in WSL2. All child processes are launched via `wsl.exe --exec` with
// argv only — never a shell. This is the security-critical boundary.

import { spawn as spawnChild, type ChildProcess } from "child_process";
import { winToWsl } from "./path-translate.ts";
import type {
  DoctorResult,
  ExecutionAdapter,
  OrmbResult,
  PlatformConfig,
} from "./types.ts";

/** Minimal App reference (avoids importing the full `obsidian` types here). */
export interface AppRef {
  vault?: { getBasePath?(): string };
}

/** Spawn signature, exposed for test injection. */
export type SpawnFn = (
  command: string,
  args: readonly string[],
  options: Record<string, unknown>,
) => ChildProcess;

/** CLI schema version expected from `doctor`. Used only for skew warnings. */
export const MIN_SCHEMA_VERSION = 1;

/** Raw outcome of a single CLI invocation, before shape-mapping. */
interface RawOutcome {
  ok: boolean;
  exitCode: number | null;
  stdout: string;
  stderr: string;
  raw: unknown;
}

function buildArgv(config: PlatformConfig, args: readonly string[]): string[] {
  const argv: string[] = [];
  // Optional distro selector — only when configured. Keeps the binding spec's
  // argv shape while making the `distro` setting functional.
  if (config.distro && config.distro.trim() !== "") {
    argv.push("--distribution", config.distro);
  }
  argv.push(
    "--exec",
    config.pythonBin,
    "-m",
    "obsidian_rm_bridge",
    ...args,
  );
  return argv;
}

/**
 * WSL execution adapter. Launches `wsl.exe --exec <pythonBin> -m
 * obsidian_rm_bridge <args>`. argv-only — never a shell, never a shell-string
 * invocation (no sh -c style, no cmd.exe shell). This is the security boundary.
 */
export class WslAdapter implements ExecutionAdapter {
  private readonly config: PlatformConfig;
  private readonly spawnFn: SpawnFn;
  /** Currently running child, if any. Used by onunload to abort it. */
  child: ChildProcess | null = null;

  constructor(config: PlatformConfig, _app: AppRef, spawnFn?: SpawnFn) {
    this.config = config;
    this.spawnFn = spawnFn ?? (spawnChild as unknown as SpawnFn);
  }

  /** Build the argv that would be passed to wsl.exe (exposed for diagnostics). */
  argvFor(args: readonly string[]): string[] {
    return buildArgv(this.config, args);
  }

  spawn(args: string[]): Promise<OrmbResult> {
    return this.spawnRaw(args).then((o) => this.toOrmbResult(o));
  }

  async doctor(): Promise<DoctorResult> {
    const o = await this.spawnRaw(["doctor", "--json"]);
    if (o.exitCode !== 0) {
      return {
        ok: false,
        version: "",
        schema_version: 0,
        rmapi: { path: "", version: "", found: false },
        chromium: "unknown",
        vault: "unknown",
        paired: false,
        key_present: false,
        errors: [o.stderr.trim() || `ormb exited with code ${o.exitCode}`],
      };
    }
    const text = o.stdout.trim();
    if (text === "") {
      return {
        ok: false,
        version: "",
        schema_version: 0,
        rmapi: { path: "", version: "", found: false },
        chromium: "unknown",
        vault: "unknown",
        paired: false,
        key_present: false,
        errors: ["doctor produced no output"],
      };
    }
    try {
      return JSON.parse(text) as DoctorResult;
    } catch {
      return {
        ok: false,
        version: "",
        schema_version: 0,
        rmapi: { path: "", version: "", found: false },
        chromium: "unknown",
        vault: "unknown",
        paired: false,
        key_present: false,
        errors: [`doctor returned non-JSON: ${text}`],
      };
    }
  }

  translateVaultRoot(windowsPath: string): string {
    return winToWsl(windowsPath, this.config.automountRoot);
  }

  /** Abort the running child, if any. Called from Plugin.onunload. */
  abort(): void {
    if (this.child && !this.child.killed) {
      this.child.kill();
    }
    this.child = null;
  }

  // --- internals ---------------------------------------------------------

  private spawnRaw(args: readonly string[]): Promise<RawOutcome> {
    return new Promise((resolve) => {
      const argv = buildArgv(this.config, args);
      const env: Record<string, string | undefined> = {
        ...process.env,
        WSL_UTF8: "1",
        PYTHONIOENCODING: "utf-8",
        NO_COLOR: "1",
      };
      // Vision model is a config/env value (`ORB_VISION_MODEL`), not a CLI flag.
      // Inject it into the child env when set so the CLI picks it up (pull path).
      if (this.config.visionModel && this.config.visionModel.trim() !== "") {
        env.ORB_VISION_MODEL = this.config.visionModel;
      }
      const child = this.spawnFn("wsl.exe", argv, {
        windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"],
        env,
      });
      this.child = child;

      let stdout = "";
      let stderr = "";

      child.stdout?.on("data", (d: Buffer) => {
        stdout += d.toString("utf-8");
      });
      child.stderr?.on("data", (d: Buffer) => {
        stderr += d.toString("utf-8");
      });

      child.on("error", (err: Error) => {
        this.child = null;
        resolve({
          ok: false,
          exitCode: null,
          stdout,
          stderr: err.message,
          raw: null,
        });
      });

      child.on("close", (code: number | null) => {
        this.child = null;
        let raw: unknown = null;
        const text = stdout.trim();
        if (text !== "") {
          try {
            raw = JSON.parse(text);
          } catch {
            raw = null;
          }
        }
        resolve({ ok: code === 0, exitCode: code, stdout, stderr, raw });
      });
    });
  }

  private toOrmbResult(o: RawOutcome): OrmbResult {
    if (o.exitCode !== 0) {
      return {
        ok: false,
        code: "cli_error",
        message: o.stderr.trim() || `ormb exited with code ${o.exitCode}`,
        data: null,
      };
    }
    const r = o.raw as Record<string, unknown> | null;
    if (
      r &&
      typeof r.ok === "boolean" &&
      typeof r.code === "string"
    ) {
      return {
        ok: r.ok as boolean,
        code: r.code as string,
        message: typeof r.message === "string" ? r.message : "",
        data:
          (r.data as OrmbResult["data"]) === null ||
          r.data === undefined
            ? null
            : (r.data as OrmbResult["data"]),
      };
    }
    return {
      ok: false,
      code: "cli_error",
      message: `Unexpected output: ${o.stdout.trim()}`,
      data: null,
    };
  }
}
