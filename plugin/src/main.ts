// Obsidian reMarkable Bridge — plugin entrypoint (Phase 5a: publish, T-WSL).
//
// The plugin is a thin TypeScript wrapper around the `ormb` CLI. It holds no
// secrets; the OpenRouter API key and rmapi token live in the CLI's 0600 config
// inside WSL home. Every CLI invocation goes through an ExecutionAdapter that
// launches `wsl.exe --exec` with argv only — never a shell.

import { Notice, Plugin, TFile } from "obsidian";
import { WslAdapter, type AppRef } from "./wsl-adapter.ts";
import { VaultBridge } from "./vault.ts";
import {
  DEFAULT_SETTINGS,
  OrmbSettingsTab,
  type OrmbSettingsWithDefaults,
} from "./settings.ts";
import type { OrmbResult, PlatformConfig } from "./types.ts";

const PUBLISH_NOTICE_OK = (msg: string) => `Published ✓ ${msg}`;
const PUBLISH_BUSY = "Publish to reMarkable already in progress — please wait.";

/** Map an OrmbResult code to a user-facing Notice. */
function noticeForResult(res: OrmbResult): void {
  if (res.ok) {
    new Notice(PUBLISH_NOTICE_OK(res.message));
    return;
  }
  const tips: Record<string, string> = {
    not_paired: "reMarkable not paired. Run 'ormb pair' in your WSL terminal.",
    key_missing:
      "OpenRouter API key not configured. Run 'ormb config set-key' in your WSL terminal.",
    rmapi_missing: "rmapi not found. Run 'ormb setup --rmapi' in your WSL terminal.",
    chromium_missing: "Playwright Chromium not installed. Run 'ormb setup' in your WSL terminal.",
    doc_exists:
      "Document already on reMarkable. Use 'ormb publish --on-exists content-only' in terminal to update.",
    note_not_found: "Source note not found in vault.",
    path_containment: "Path rejected: outside vault.",
    spawn_failed: "Could not launch ormb. Check Settings → Test connection.",
    rate_limited: "OpenRouter rate limited. Wait and retry.",
    cli_error: `ormb error: ${res.message}`,
  };
  new Notice(tips[res.code] ?? `ormb error: ${res.message}`);
}

export default class ObsidianRmBridgePlugin extends Plugin {
  settings!: OrmbSettingsWithDefaults;
  adapter!: WslAdapter;
  private vaultBridge!: VaultBridge;
  private publishing = false;

  async onload(): Promise<void> {
    await this.loadSettings();

    this.adapter = new WslAdapter(this.platformConfig(), this.app as unknown as AppRef);
    this.vaultBridge = new VaultBridge(
      this.app as unknown as { vault: { getBasePath(): string } },
      this.platformConfig(),
    );

    // Surface doctor warnings on load (silent when healthy).
    void this.runDoctor();

    this.addCommand({
      id: "publish-to-remarkable",
      name: "Publish to reMarkable",
      editorCallback: (_editor, ctx) => {
        const file = ctx.file ?? this.app.workspace.getActiveFile();
        if (file) void this.publish(file);
      },
    });

    this.addRibbonIcon("up-arrow-with-tail", "Publish to reMarkable", () => {
      const file = this.app.workspace.getActiveFile();
      if (file) void this.publish(file);
    });

    this.registerEvent(
      this.app.workspace.on("file-menu", (menu, file) => {
        if (!(file instanceof TFile)) return;
        menu.addItem((item) => {
          item
            .setTitle("Publish to reMarkable")
            .setIcon("up-arrow-with-tail")
            .onClick(() => void this.publish(file));
        });
      }),
    );

    this.addSettingTab(new OrmbSettingsTab(this.app, this));
  }

  onunload(): void {
    // Abort any in-flight CLI child process so we don't orphan it.
    this.adapter?.abort();
  }

  /** Derive the adapter config from persisted settings. */
  platformConfig(): PlatformConfig {
    const s = this.settings ?? DEFAULT_SETTINGS;
    return {
      launcher: s.launcher,
      distro: s.distro,
      pythonBin: s.pythonBin,
      rmFolder: s.rmFolder,
      visionModel: s.visionModel,
      automountRoot: s.automountRoot,
    };
  }

  async loadSettings(): Promise<void> {
    this.settings = Object.assign(
      {},
      DEFAULT_SETTINGS,
      await this.loadData(),
    ) as OrmbSettingsWithDefaults;
  }

  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
  }

  /** Rebuild the adapter after settings change (e.g. pythonBin, distro). */
  refreshAdapter(): void {
    this.adapter = new WslAdapter(this.platformConfig(), this.app as unknown as AppRef);
    this.vaultBridge = new VaultBridge(
      this.app as unknown as { vault: { getBasePath(): string } },
      this.platformConfig(),
    );
  }

  /** Publish the given note to reMarkable. Single-flight guarded. */
  async publish(file: TFile): Promise<void> {
    if (this.publishing) {
      new Notice(PUBLISH_BUSY);
      return;
    }

    // Reject suspicious paths before handing them to the child process.
    if (!file.path || file.path.includes("\0") || file.path.includes("..")) {
      new Notice("Refusing to publish: invalid note path.");
      return;
    }

    // Save the dirty editor if a save method is available (Obsidian autosaves,
    // but be explicit per the spec).
    await this.saveActiveEditorIfDirty();

    this.publishing = true;
    try {
      const vaultRoot = this.vaultBridge.vaultPathLinux;
      const args = [
        "publish",
        file.path,
        "--vault",
        vaultRoot,
        "--json",
        "--rm-folder",
        this.settings.rmFolder,
      ];
      const res = await this.adapter.spawn(args);
      noticeForResult(res);
    } catch (err) {
      new Notice(`Publish failed: ${(err as Error).message}`);
    } finally {
      this.publishing = false;
    }
  }

  /** Run `ormb doctor` and surface warnings. Silent when healthy unless `always`. */
  async runDoctor(always = false): Promise<void> {
    try {
      const doc = await this.adapter.doctor();
      if (!doc.ok || doc.errors.length > 0) {
        for (const e of doc.errors) new Notice(`ormb doctor: ${e}`);
        if (!doc.paired) new Notice("reMarkable not paired. Run 'ormb pair' in your WSL terminal.");
        if (!doc.key_present) new Notice("OpenRouter key not set. Run 'ormb config set-key' in your WSL terminal.");
      } else if (always) {
        new Notice("ormb: all checks passed ✓");
      }
    } catch (err) {
      if (always) new Notice(`ormb doctor failed: ${(err as Error).message}`);
    }
  }

  private async saveActiveEditorIfDirty(): Promise<void> {
    // Obsidian autosaves, but the spec asks us to be explicit. The public
    // `Editor` type has no `save()`, so duck-type it to stay type-safe.
    const leaf = this.app.workspace.activeLeaf as
      | { view?: { editor?: { save?: () => void } } }
      | undefined;
    const editor = leaf?.view?.editor;
    if (editor && typeof editor.save === "function") {
      try {
        editor.save();
      } catch {
        /* Obsidian autosaves; ignore. */
      }
    }
  }
}
