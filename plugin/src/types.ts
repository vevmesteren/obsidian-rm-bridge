// Type definitions for the Obsidian reMarkable Bridge plugin.
//
// The plugin is a thin wrapper around the `ormb` CLI (`python -m
// obsidian_rm_bridge`). It never stores secrets; the OpenRouter API key and
// rmapi token live in the CLI's 0600 config inside WSL home.

/** Configuration that selects how the CLI is launched on this platform. */
export interface PlatformConfig {
  /** Free-form launcher label, e.g. "python -m obsidian_rm_bridge" or "ormb". */
  launcher: string;
  /** WSL distribution name (T-WSL). Empty for non-WSL topologies. */
  distro: string;
  /** Absolute path to the python interpreter, in the CLI's filesystem. */
  pythonBin: string;
  /** reMarkable destination folder, e.g. "/Obsidian". */
  rmFolder: string;
  /** Vision model slug for pulls, e.g. "z-ai/glm-4.5v". Empty = CLI default. */
  visionModel: string;
  /** WSL automount root, e.g. "/mnt". Used to translate Windows → WSL paths. */
  automountRoot: string;
}

/** Payload returned by `ormb publish --json` on success. */
export interface OrmbPublishData {
  name: string;
  folder: string;
  dest: string;
  pages: number;
}

/** JSON result envelope emitted by the CLI on stdout when `--json` is passed. */
export interface OrmbResult {
  ok: boolean;
  code: string;
  message: string;
  data: OrmbPublishData | null;
}

/** JSON envelope emitted by `ormb doctor --json`. */
export interface DoctorResult {
  ok: boolean;
  version: string;
  schema_version: number;
  rmapi: { path: string; version: string; found: boolean };
  chromium: string;
  vault: string;
  paired: boolean;
  key_present: boolean;
  errors: string[];
}

/**
 * One implementation per topology. The plugin holds a single adapter instance,
 * selected at doctor time, and every command goes through it.
 */
export interface ExecutionAdapter {
  spawn(args: string[]): Promise<OrmbResult>;
  doctor(): Promise<DoctorResult>;
  translateVaultRoot(windowsPath: string): string;
}

/** Persisted plugin settings (data.json). NO secrets — no API key field. */
export interface OrmbSettings {
  launcher: string;
  distro: string;
  pythonBin: string;
  rmFolder: string;
  visionModel: string;
  automountRoot: string;
}
