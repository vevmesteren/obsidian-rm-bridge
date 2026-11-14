// Obsidian reMarkable Bridge — plugin entrypoint (Phase 5a: publish, T-WSL).
//
// The plugin is a thin TypeScript wrapper around the `ormb` CLI. It holds no
// secrets; the OpenRouter API key and rmapi token live in the CLI's 0600 config
// inside WSL home. Every CLI invocation goes through an ExecutionAdapter that
// launches `wsl.exe --exec` with argv only — never a shell.

import { Modal, Notice, Plugin, TFile } from "obsidian";
import { WslAdapter, type AppRef } from "./wsl-adapter.ts";
import { NativeAdapter } from "./native-adapter.ts";
import { VaultBridge, type VaultApp } from "./vault.ts";
import { buildPullArgs } from "./pull-args.ts";
import {
  applyMarkerBlock,
  buildConsentBody,
  buildMarkerBlock,
  DEFAULT_VISION_MODEL,
} from "./marker-block.ts";
import {
  buildRepublishBody,
  noticeTimeout,
  NOTICE_OK_TIMEOUT,
  NOTICE_WARN_TIMEOUT,
} from "./notice.ts";
import {
  DEFAULT_SETTINGS,
  OrmbSettingsTab,
  type OrmbSettingsWithDefaults,
} from "./settings.ts";
import { defaultTopologyContext, detectTopology } from "./topology.ts";
import type {
  ExecutionAdapter,
  OrmbPullData,
  OrmbResult,
  PlatformConfig,
  Topology,
} from "./types.ts";

const PUBLISH_NOTICE_OK = (msg: string) => `Published ✓ ${msg}`;
const PULL_NOTICE_OK = (msg: string) => `Pulled ✓ ${msg}`;
const PUBLISH_BUSY = "Publish to reMarkable already in progress — please wait.";
const PULL_BUSY = "Pull already in progress — please wait.";

/** Map an OrmbResult code to a user-facing Notice with an appropriate timeout. */
function noticeForResult(res: OrmbResult, verb: "Published" | "Pulled" = "Published"): void {
  if (res.ok) {
    const prefix = verb === "Pulled" ? PULL_NOTICE_OK : PUBLISH_NOTICE_OK;
    new Notice(prefix(res.message), NOTICE_OK_TIMEOUT);
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
  new Notice(tips[res.code] ?? `ormb error: ${res.message}`, noticeTimeout(res));
}

export default class ObsidianRmBridgePlugin extends Plugin {
  settings!: OrmbSettingsWithDefaults;
  adapter!: ExecutionAdapter;
  private vaultBridge!: VaultBridge;
  private publishing = false;
  /** Status bar item showing live CLI progress (rendering, uploading…). */
  private statusItem!: HTMLElement;
  /** The resolved (non-'auto') topology currently in use. */
  activeTopology: Topology = "wsl";

  async onload(): Promise<void> {
    await this.loadSettings();

    this.statusItem = this.addStatusBarItem();
    this.statusItem.setText("");

    this.activeTopology = this.resolveTopology();
    this.adapter = this.makeAdapter();
    this.vaultBridge = new VaultBridge(
      this.app as unknown as VaultApp,
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

    this.addCommand({
      id: "pull-annotations",
      name: "Pull annotations from reMarkable",
      editorCallback: (_editor, ctx) => {
        const file = ctx.file ?? this.app.workspace.getActiveFile();
        if (file) void this.pullAnnotations(file);
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
        menu.addItem((item) => {
          item
            .setTitle("Pull annotations from reMarkable")
            .setIcon("down-arrow-with-tail")
            .onClick(() => void this.pullAnnotations(file));
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
      topology: s.topology,
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

  /** Resolve the effective (non-'auto') topology from settings or detection. */
  private resolveTopology(): Topology {
    const s = this.settings ?? DEFAULT_SETTINGS;
    if (s.topology && s.topology !== "auto") return s.topology;
    return detectTopology(defaultTopologyContext());
  }

  /** Build the adapter matching the active topology. */
  private makeAdapter(): ExecutionAdapter {
    const cfg = this.platformConfig();
    const appRef = this.app as unknown as AppRef;
    if (this.activeTopology === "wsl") {
      return new WslAdapter(cfg, appRef);
    }
    return new NativeAdapter(cfg, appRef);
  }

  /** Rebuild the adapter after settings change (e.g. pythonBin, distro, topology). */
  refreshAdapter(): void {
    this.activeTopology = this.resolveTopology();
    this.adapter = this.makeAdapter();
    this.vaultBridge = new VaultBridge(
      this.app as unknown as VaultApp,
      this.platformConfig(),
    );
  }

  /** Publish the given note to reMarkable. Single-flight guarded. */
  async publish(file: TFile): Promise<void> {
    if (this.publishing) {
      new Notice(PUBLISH_BUSY, NOTICE_WARN_TIMEOUT);
      return;
    }

    // Reject suspicious paths before handing them to the child process.
    // Check for ".." as a path segment, not substring (avoids false-positive
    // on filenames like "foo..bar.md") (grok).
    const segments = file.path.split("/");
    if (!file.path || file.path.includes("\0") || segments.includes("..")) {
      new Notice("Refusing to publish: invalid note path.", NOTICE_WARN_TIMEOUT);
      return;
    }

    // Save the dirty editor if a save method is available (Obsidian autosaves,
    // but be explicit per the spec).
    await this.saveActiveEditorIfDirty();

    this.publishing = true;
    try {
      const vaultRoot = this.vaultBridge.vaultPathLinux;
      const res = await this.runPublish(file, vaultRoot, "fail");
      if (res.code === "doc_exists" && !res.ok) {
        const replace = await this.showRepublishModal(file);
        if (replace) {
          const res2 = await this.runPublish(file, vaultRoot, "content-only");
          noticeForResult(res2);
        }
        return;
      }
      noticeForResult(res);
    } catch (err) {
      new Notice(`Publish failed: ${(err as Error).message}`, NOTICE_WARN_TIMEOUT);
    } finally {
      this.publishing = false;
      this.statusItem.setText("");
    }
  }

  /** Spawn the publish command with a given --on-exists mode, surfacing
   * progress on the status bar. */
  private async runPublish(
    file: TFile,
    vaultRoot: string,
    onExists: "fail" | "content-only",
  ): Promise<OrmbResult> {
    const args = [
      "publish",
      file.path,
      "--vault",
      vaultRoot,
      "--json",
      "--on-exists",
      onExists,
      "--rm-folder",
      this.settings.rmFolder,
    ];
    return this.adapter.spawn(args, (line) => {
      this.statusItem.setText(`ormb: ${line}`);
    });
  }

  /** Run `ormb doctor` and surface warnings. Silent when healthy unless `always`. */
  async runDoctor(always = false): Promise<void> {
    try {
      const doc = await this.adapter.doctor();
      if (!doc.ok || doc.errors.length > 0) {
        for (const e of doc.errors) new Notice(`ormb doctor: ${e}`, NOTICE_WARN_TIMEOUT);
        if (!doc.paired) new Notice("reMarkable not paired. Run 'ormb pair' in your WSL terminal.", NOTICE_WARN_TIMEOUT);
        if (!doc.key_present) new Notice("OpenRouter key not set. Run 'ormb config set-key' in your WSL terminal.", NOTICE_WARN_TIMEOUT);
      } else if (always) {
        new Notice("ormb: all checks passed ✓", NOTICE_OK_TIMEOUT);
      }
    } catch (err) {
      if (always) new Notice(`ormb doctor failed: ${(err as Error).message}`, NOTICE_WARN_TIMEOUT);
    }
  }

  /** Pull handwritten annotations from reMarkable into the note. Single-flight guarded. */
  async pullAnnotations(file: TFile): Promise<void> {
    if (this.publishing) {
      new Notice(PULL_BUSY, NOTICE_WARN_TIMEOUT);
      return;
    }

    // Path safety (same guard as publish).
    const segments = file.path.split("/");
    if (!file.path || file.path.includes("\0") || segments.includes("..")) {
      new Notice("Refusing to pull: invalid note path.", NOTICE_WARN_TIMEOUT);
      return;
    }

    // Save the dirty editor before we read/write via vault.process — pull
    // reads on-disk content and writes back, so unsaved buffer edits would
    // otherwise be overwritten (same rationale as publish).
    await this.saveActiveEditorIfDirty();

    // Best-effort page count via `pull --info` (NO vision, NO OpenRouter cost —
    // just downloads the PDF and counts pages). Falls back to no count on any
    // failure so the consent modal still shows (AC-6).
    const pageCount = await this.fetchPageCount(file);

    // First-run consent: OpenRouter egress disclosure. Sticky once given.
    if (!this.settings.pullConsentGiven) {
      const consent = await this.showPullConsentModal(file, pageCount);
      if (!consent) return;
      this.settings.pullConsentGiven = true;
      await this.saveSettings();
    }

    this.publishing = true;
    try {
      const vaultRoot = this.vaultBridge.vaultPathLinux;
      const args = buildPullArgs(file, vaultRoot, this.settings.rmFolder);
      // Best-effort status bar from stderr lines (transcription progress).
      const progressLines: string[] = [];
      const res = await this.adapter.spawn(args, (line) => {
        progressLines.push(line);
        this.statusItem.setText(`ormb: ${line}`);
      });
      if (res.ok && res.code === "transcribed" && res.data) {
        // Validate that res.data is OrmbPullData, not OrmbPublishData (grok).
        const d = res.data as Record<string, unknown>;
        if (!("sections" in d) || !Array.isArray(d.sections)) {
          noticeForResult(res, "Pulled");
        } else {
          const pullData = res.data as OrmbPullData;
          // Guard against empty pulls — don't wipe existing annotations if
          // the transcription returned nothing (grok C1).
          if (
            !pullData.sections || pullData.sections.length === 0 ||
            pullData.annotated_pages === 0
          ) {
            new Notice("No annotations found — existing annotations preserved.", NOTICE_WARN_TIMEOUT);
          } else {
            const markerBlock = buildMarkerBlock(pullData);
            // Atomic, undo-able write: vault.process reads current content and
            // applies the replace-not-duplicate transform in one step.
            await this.app.vault.process(file, (current) =>
              applyMarkerBlock(current, markerBlock, pullData),
            );
            new Notice(`Pulled ${pullData.annotated_pages} annotation(s) ✓`, NOTICE_OK_TIMEOUT);
          }
        }
      } else {
        noticeForResult(res, "Pulled");
      }
    } catch (err) {
      new Notice(`Pull failed: ${(err as Error).message}`, NOTICE_WARN_TIMEOUT);
    } finally {
      this.publishing = false;
      this.statusItem.setText("");
    }
  }

  /**
   * Best-effort `ormb pull --info <page_name> --json`. Returns the PDF page
   * count WITHOUT invoking vision (no OpenRouter cost). Returns null on any
   * failure so the consent modal still shows (AC-6).
   */
  private async fetchPageCount(file: TFile): Promise<number | null> {
    try {
      const vaultRoot = this.vaultBridge.vaultPathLinux;
      const args = [
        "pull",
        file.basename,
        "--info",
        "--vault",
        vaultRoot,
        "--rm-folder",
        this.settings.rmFolder,
        "--json",
      ];
      const res = await this.adapter.spawn(args);
      if (res.ok && res.data) {
        const d = res.data as Record<string, unknown>;
        if (typeof d.total_pages === "number") {
          return d.total_pages;
        }
      }
      return null;
    } catch {
      return null;
    }
  }

  /** First-run consent modal for the pull path (OpenRouter egress). */
  private showPullConsentModal(file: TFile, pageCount: number | null = null): Promise<boolean> {
    return new Promise((resolve) => {
      const modal = new Modal(this.app);
      modal.titleEl.setText("Pull annotations from reMarkable");
      const content = modal.contentEl;
      const body = buildConsentBody(
        file.basename,
        this.settings.visionModel || DEFAULT_VISION_MODEL,
        pageCount,
      );
      content.createEl("p", { text: body });
      content.createEl("p", {
        text:
          "This is disclosed and consented to on first pull. " +
          "You can revoke by clearing the consent toggle in settings.",
        cls: "setting-item-description",
      });

      const btnBar = content.createDiv({ cls: "modal-button-bar" });
      const cancelBtn = btnBar.createEl("button", { text: "Cancel" });
      const okBtn = btnBar.createEl("button", {
        text: "Consent & Pull",
        cls: "mod-cta",
      });

      // Resolve exactly once: Obsidian modals can be dismissed via Escape or
      // backdrop click (which call modal.close() without firing either button
      // handler). Treat any non-OK dismissal as a cancellation so the awaited
      // promise never hangs.
      let resolved = false;
      const done = (v: boolean): void => {
        if (resolved) return;
        resolved = true;
        resolve(v);
      };
      okBtn.onclick = () => {
        done(true);
        modal.close();
      };
      cancelBtn.onclick = () => {
        done(false);
        modal.close();
      };
      modal.onClose = () => done(false);
      modal.open();
    });
  }

  /**
   * Republish confirmation modal (AC-2). Shown when publish returns
   * `doc_exists`. The default publish uses `--on-exists fail`; the replace is
   * explicit and preserves reMarkable annotations via `--on-exists
   * content-only`. Returns true if the user confirms replace.
   */
  private showRepublishModal(file: TFile): Promise<boolean> {
    return new Promise((resolve) => {
      const modal = new Modal(this.app);
      modal.titleEl.setText("Document already exists on reMarkable");
      const content = modal.contentEl;
      content.createEl("p", { text: buildRepublishBody(file.basename) });

      const btnBar = content.createDiv({ cls: "modal-button-bar" });
      const cancelBtn = btnBar.createEl("button", { text: "Cancel" });
      const okBtn = btnBar.createEl("button", {
        text: "Replace",
        cls: "mod-warning",
      });

      let resolved = false;
      const done = (v: boolean): void => {
        if (resolved) return;
        resolved = true;
        resolve(v);
      };
      okBtn.onclick = () => {
        done(true);
        modal.close();
      };
      cancelBtn.onclick = () => {
        done(false);
        modal.close();
      };
      modal.onClose = () => done(false);
      modal.open();
    });
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
