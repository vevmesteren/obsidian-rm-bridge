// ExecutionAdapter for native topologies (T-MAC, T-LINUX, T-WIN): Obsidian and
// the ormb CLI share one filesystem. The CLI is launched directly as
// `<pythonBin> -m obsidian_rm_bridge <args>` with argv only — never a shell.
// This is the security-critical boundary (ARB R1, invariant 1).

import { spawn as spawnChild, type ChildProcess } from "child_process";
import type { SpawnFn, AppRef } from "./wsl-adapter.ts";
import type {
  DoctorResult,
  ExecutionAdapter,
  OrmbResult,
  PlatformConfig,
} from "./types.ts";

/** Raw outcome of a single CLI invocation, before shape-mapping. */
interface RawOutcome {
  ok: boolean;
  exitCode: number | null;
  stdout: string;
  stderr: string;
  raw: unknown;
}

/**
 * Native execution adapter. Launches `<pythonBin> -m obsidian_rm_bridge
 * <args>`. argv-only — never a shell. The same env/stdio pattern as WslAdapter
 * minus the wsl.exe / --distribution / --exec trappings and the WSLENV
 * forwarding (no Windows→Linux boundary to cross).
 */
export class NativeAdapter implements ExecutionAdapter {
  private readonly config: PlatformConfig;
  private readonly spawnFn: SpawnFn;
  /** Currently running child, if any. Used by onunload to abort it. */
  child: ChildProcess | null = null;

  constructor(config: PlatformConfig, _app: AppRef, spawnFn?: SpawnFn) {
    this.config = config;
    this.spawnFn = spawnFn ?? (spawnChild as unknown as SpawnFn);
  }

  spawn(args: string[], onStderr?: (line: string) => void): Promise<OrmbResult> {
    return this.spawnRaw(args, onStderr).then((o) => this.toOrmbResult(o));
  }

  async doctor(): Promise<DoctorResult> {
    const o = await this.spawnRaw(["doctor", "--json"]);
    const text = o.stdout.trim();
    if (text !== "") {
      try {
        return JSON.parse(text) as DoctorResult;
      } catch {
        // fall through to empty result below
      }
    }
    return {
      ok: false,
      version: "",
      schema_version: 0,
      rmapi: { path: "", version: "", found: false },
      chromium: "unknown",
      vault: "unknown",
      paired: false,
      key_present: false,
      errors: [o.stderr.trim() || `doctor exited with code ${o.exitCode}`],
    };
  }

  /** No path translation on native topologies — the CLI sees the same FS. */
  translateVaultRoot(windowsPath: string): string {
    return windowsPath;
  }

  /** Abort the running child, if any. Called from Plugin.onunload. */
  abort(): void {
    if (this.child && !this.child.killed) {
      this.child.kill();
    }
    this.child = null;
  }

  // --- internals ---------------------------------------------------------

  private spawnRaw(
    args: readonly string[],
    onStderr?: (line: string) => void,
  ): Promise<RawOutcome> {
    return new Promise((resolve) => {
      const argv = ["-m", "obsidian_rm_bridge", ...args];
      const env: Record<string, string | undefined> = {
        ...process.env,
        PYTHONIOENCODING: "utf-8",
        NO_COLOR: "1",
      };
      // Vision model is a config/env value (`ORB_VISION_MODEL`), not a CLI flag.
      // On native topologies there is no WSLENV boundary to cross.
      if (this.config.visionModel && this.config.visionModel.trim() !== "") {
        env.ORB_VISION_MODEL = this.config.visionModel;
      }
      const child = this.spawnFn(this.config.pythonBin, argv, {
        windowsHide: true,
        shell: false,
        stdio: ["ignore", "pipe", "pipe"],
        env,
      });
      this.child = child;

      let stdout = "";
      let stderr = "";
      let stderrPending = "";

      child.stdout?.on("data", (d: Buffer) => {
        stdout += d.toString("utf-8");
      });
      child.stderr?.on("data", (d: Buffer) => {
        const chunk = d.toString("utf-8");
        stderr += chunk;
        if (onStderr) {
          stderrPending += chunk;
          const lines = stderrPending.split("\n");
          stderrPending = lines.pop() ?? "";
          for (const line of lines) {
            if (line.length > 0) onStderr(line);
          }
        }
      });

      child.on("error", (err: Error) => {
        this.child = null;
        resolve({ ok: false, exitCode: null, stdout, stderr: err.message, raw: null });
      });

      child.on("close", (code: number | null) => {
        this.child = null;
        if (onStderr && stderrPending.length > 0) {
          onStderr(stderrPending);
          stderrPending = "";
        }
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
    const r = o.raw as Record<string, unknown> | null;
    if (r && typeof r.ok === "boolean" && typeof r.code === "string") {
      return {
        ok: r.ok as boolean,
        code: r.code as string,
        message: typeof r.message === "string" ? r.message : "",
        data:
          (r.data as OrmbResult["data"]) === null || r.data === undefined
            ? null
            : (r.data as OrmbResult["data"]),
      };
    }
    return {
      ok: false,
      code: "cli_error",
      message: o.stderr.trim() || `ormb exited with code ${o.exitCode}`,
      data: null,
    };
  }
}
