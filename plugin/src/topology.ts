// Platform topology detection (Phase 5c, AC-5).
//
// Selects which ExecutionAdapter the plugin uses. The detection is best-effort
// and overridable via the settings dropdown. The WSL check looks for wsl.exe
// or the WSL_DISTRO_NAME env var; on any failure it defaults to 'win' on
// Windows (the native Windows topology, no WSL).

import { existsSync } from "fs";
import type { Topology } from "./types.ts";

/** Injectable context so detectTopology is unit-testable without monkey-patching globals. */
export interface TopologyContext {
  /** process.platform value, e.g. "win32", "darwin", "linux". */
  platform: string;
  /** Returns true if WSL appears to be available on this host. */
  hasWsl: () => boolean;
}

/**
 * Detect the platform topology from the given context.
 *
 * - darwin  -> mac
 * - linux   -> linux
 * - win32   -> wsl (if WSL available) else win
 * - other   -> linux (sensible default for POSIX-like hosts)
 */
export function detectTopology(ctx: TopologyContext): Topology {
  switch (ctx.platform) {
    case "darwin":
      return "mac";
    case "linux":
      return "linux";
    case "win32":
      return ctx.hasWsl() ? "wsl" : "win";
    default:
      return "linux";
  }
}

/** True if WSL appears to be installed/available on this Windows host. */
function wslAvailable(): boolean {
  try {
    // WSL_DISTRO_NAME is set inside a WSL session, but Obsidian runs on the
    // Windows host; check for wsl.exe on SystemRoot instead.
    const systemRoot = process.env.SystemRoot ?? "C:\\Windows";
    if (existsSync(`${systemRoot}\\System32\\wsl.exe`)) return true;
    if (typeof process.env.WSL_DISTRO_NAME === "string" && process.env.WSL_DISTRO_NAME !== "") {
      return true;
    }
    return false;
  } catch {
    return false;
  }
}

/**
 * Build a TopologyContext from the live environment. Used by main.ts at
 * load time; tests inject their own context.
 */
export function defaultTopologyContext(): TopologyContext {
  return {
    platform: process.platform,
    hasWsl: wslAvailable,
  };
}
