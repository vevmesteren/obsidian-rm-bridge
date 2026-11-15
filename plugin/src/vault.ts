// Vault root translation. Only the vault root is translated (once, then cached);
// note paths are passed vault-relative because Obsidian `file.path` is already
// forward-slash separated.

import { winToWsl } from "./path-translate.ts";
import type { PlatformConfig } from "./types.ts";

/** Minimal App reference so this file is unit-testable without `obsidian`.
 *
 * Obsidian's `Vault` type has no `getBasePath()`. The method lives on
 * `FileSystemAdapter` (the desktop concrete class). We duck-type it here
 * so this module stays testable without importing `obsidian`.
 */
export interface VaultApp {
  vault: {
    adapter: {
      getBasePath(): string;
    };
  };
}

/** Resolve the vault root as a Linux path (T-WSL) or as-is (native). */
export function translateVaultRoot(
  app: VaultApp,
  config: PlatformConfig,
): string {
  const base = app.vault.adapter.getBasePath();
  // Only translate for WSL topology — native topologies pass the path as-is.
  if (config.topology === "wsl" && /^[A-Za-z]:[\\/]/.test(base)) {
    return winToWsl(base, config.automountRoot);
  }
  return base;
}

/**
 * Caches the translated vault root on the plugin instance. Pass the same
 * `cache` object on every call; the translation runs at most once.
 */
export class VaultBridge {
  private cached: string | null = null;

  constructor(
    private readonly app: VaultApp,
    private readonly config: PlatformConfig,
  ) {}

  /** The vault root as seen by the CLI's filesystem. */
  get vaultPathLinux(): string {
    if (this.cached === null) {
      this.cached = translateVaultRoot(this.app, this.config);
    }
    return this.cached;
  }

  /** Invalidate the cache (e.g. after settings change). */
  invalidate(): void {
    this.cached = null;
  }
}
