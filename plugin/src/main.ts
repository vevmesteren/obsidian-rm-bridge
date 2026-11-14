// Obsidian reMarkable Bridge — plugin entrypoint (Phase 5a: publish, T-WSL).
//
// The plugin is a thin TypeScript wrapper around the `ormb` CLI. It holds no
// secrets; the OpenRouter API key and rmapi token live in the CLI's 0600 config
// inside WSL home. Every CLI invocation goes through an ExecutionAdapter that
// launches `wsl.exe --exec` with argv only — never a shell.

import { Modal, Notice, Plugin, TFile } from "obsidian";
import { WslAdapter, type AppRef } from "./wsl-adapter.ts";
import { VaultBridge, type VaultApp } from "./vault.ts";
import { buildPullArgs } from "./pull-args.ts";
import {
  applyMarkerBlock,
  buildConsentBody,
  buildMarkerBlock,
  DEFAULT_VISION_MODEL,
} from "./marker-block.ts";
import {
  DEFAULT_SETTINGS,
  OrmbSettingsTab,
  type OrmbSettingsWithDefaults,
} from "./settings.ts";
import type { OrmbPullData, OrmbResult, PlatformConfig } from "./types.ts";

const PUBLISH_NOTICE_OK = (msg: string) => `Published ✓ ${msg}`;
const PULL_NOTICE_OK = (msg: string) => `Pulled ✓ ${msg}`;
const PUBLISH_BUSY = "Publish to reMarkable already in progress — please wait.";
const PULL_BUSY = "Pull already in progress — please wait.";

/** Map an OrmbResult code to a user-facing Notice. */
function noticeForResult(res: OrmbResult, verb: "Published" | "Pulled" = "Published"): void {
  if (res.ok) {
    const prefix = verb === "Pulled" ? PULL_NOTICE_OK : PUBLISH_NOTICE_OK;
    new Notice(prefix(res.message));
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
      this.app as unknown as VaultApp,
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
    // Check for ".." as a path segment, not substring (avoids false-positive
    // on filenames like "foo..bar.md") (grok).
    const segments = file.path.split("/");
    if (!file.path || file.path.includes("\0") || segments.includes("..")) {
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
        "--on-exists",
        "fail",
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

  /** Pull handwritten annotations from reMarkable into the note. Single-flight guarded. */
  async pullAnnotations(file: TFile): Promise<void> {
    if (this.publishing) {
      new Notice(PULL_BUSY);
      return;
    }

    // Path safety (same guard as publish).
    const segments = file.path.split("/");
    if (!file.path || file.path.includes("\0") || segments.includes("..")) {
      new Notice("Refusing to pull: invalid note path.");
      return;
    }

    // Save the dirty editor before we read/write via vault.process — pull
    // reads on-disk content and writes back, so unsaved buffer edits would
    // otherwise be overwritten (same rationale as publish).
    await this.saveActiveEditorIfDirty();

    // First-run consent: OpenRouter egress disclosure. Sticky once given.
    if (!this.settings.pullConsentGiven) {
      const consent = await this.showPullConsentModal(file);
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
      });
      if (res.ok && res.code === "transcribed" && res.data) {
        // Validate that res.data is OrmbPullData, not OrmbPublishData (grok).
        const d = res.data as Record<string, unknown>;
        if (!("sections" in d) || !Array.isArray(d.sections)) {
          noticeForResult(res);
        } else {
          const pullData = res.data as OrmbPullData;
          // Guard against empty pulls — don't wipe existing annotations if
          // the transcription returned nothing (grok C1).
          if (
            !pullData.sections || pullData.sections.length === 0 ||
            pullData.annotated_pages === 0
          ) {
            new Notice("No annotations found — existing annotations preserved.");
          } else {
            const markerBlock = buildMarkerBlock(pullData);
            // Atomic, undo-able write: vault.process reads current content and
            // applies the replace-not-duplicate transform in one step.
            await this.app.vault.process(file, (current) =>
              applyMarkerBlock(current, markerBlock, pullData),
            );
            new Notice(`Pulled ${pullData.annotated_pages} annotation(s) ✓`);
          }
        }
      } else {
        noticeForResult(res, "Pulled");
      }
    } catch (err) {
      new Notice(`Pull failed: ${(err as Error).message}`);
    } finally {
      this.publishing = false;
    }
  }

  /** First-run consent modal for the pull path (OpenRouter egress). */
  private showPullConsentModal(file: TFile): Promise<boolean> {
    return new Promise((resolve) => {
      const modal = new Modal(this.app);
      modal.titleEl.setText("Pull annotations from reMarkable");
      const content = modal.contentEl;
      const body = buildConsentBody(
        file.basename,
        this.settings.visionModel || DEFAULT_VISION_MODEL,
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
