// Settings tab for the Obsidian reMarkable Bridge plugin.
//
// NO API KEY FIELD — by design. The OpenRouter API key lives in the CLI's 0600
// `config.toml` inside WSL home; the plugin never stores, reads, or transmits
// secrets. Setup/pair/set-key stay terminal-only and are surfaced here as
// copyable commands.

import { Notice, PluginSettingTab, Setting } from "obsidian";
import type ObsidianRmBridgePlugin from "./main.ts";
import type { DoctorResult } from "./types.ts";

export const DEFAULT_SETTINGS = {
  launcher: "python -m obsidian_rm_bridge",
  distro: "Ubuntu",
  pythonBin: "/home/u/.venvs/ormb/bin/python",
  rmFolder: "/Obsidian",
  visionModel: "",
  automountRoot: "/mnt",
  pullConsentGiven: false,
};

export type OrmbSettingsWithDefaults = typeof DEFAULT_SETTINGS;

const COPYABLE_COMMANDS: { label: string; command: string }[] = [
  { label: "Pair reMarkable", command: "ormb pair" },
  { label: "Install rmapi", command: "ormb setup --rmapi" },
  { label: "Install Playwright Chromium", command: "ormb setup" },
  { label: "Set OpenRouter API key (stdin)", command: "ormb config set-key" },
];

/** Render a DoctorResult as a compact status grid (plain DOM, no secret data). */
function renderStatusGrid(container: HTMLElement, doc: DoctorResult): void {
  container.empty();
  const rows: [string, string][] = [
    ["ormb version", doc.version || "—"],
    ["schema version", String(doc.schema_version || "—")],
    ["rmapi", doc.rmapi?.found ? `found (${doc.rmapi.version})` : "missing"],
    ["chromium", doc.chromium || "unknown"],
    ["vault", doc.vault || "unknown"],
    ["paired", doc.paired ? "yes" : "no"],
    ["api key present", doc.key_present ? "yes" : "no"],
  ];
  for (const [k, v] of rows) {
    const row = container.createEl("div", { cls: "ormb-status-row" });
    row.createEl("span", { text: k, cls: "ormb-status-key" });
    row.createEl("span", { text: v, cls: "ormb-status-val" });
  }
  if (doc.errors.length > 0) {
    const errs = container.createEl("div", { cls: "ormb-status-errors" });
    for (const e of doc.errors) errs.createEl("div", { text: `• ${e}` });
  }
}

export class OrmbSettingsTab extends PluginSettingTab {
  declare plugin: ObsidianRmBridgePlugin;
  private statusHost: HTMLElement;

  constructor(app: import("obsidian").App, plugin: ObsidianRmBridgePlugin) {
    super(app, plugin);
    this.plugin = plugin;
    this.statusHost = document.createElement("div");
    this.statusHost.className = "ormb-status-grid";
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    containerEl.createEl("h3", { text: "Obsidian reMarkable Bridge" });
    containerEl.createEl("p", {
      text: "The plugin wraps the ormb CLI in WSL. No API key is stored here — it lives in the CLI's 0600 config inside your WSL home.",
      cls: "setting-item-description",
    });

    // --- Launcher ---------------------------------------------------------
    new Setting(containerEl)
      .setName("Launcher")
      .setDesc("How the ormb CLI is invoked.")
      .addDropdown((dd) => {
        dd.addOption("python -m obsidian_rm_bridge", "python -m obsidian_rm_bridge");
        dd.addOption("ormb", "ormb");
        dd.setValue(this.plugin.settings.launcher);
        dd.onChange(async (v) => {
          this.plugin.settings.launcher = v;
          await this.plugin.saveSettings();
        });
      });

    // --- Distro -----------------------------------------------------------
    new Setting(containerEl)
      .setName("WSL distribution")
      .setDesc("WSL distro name passed to wsl.exe --distribution. Leave empty for the default distro.")
      .addText((t) => {
        t.setValue(this.plugin.settings.distro);
        t.onChange(async (v) => {
          this.plugin.settings.distro = v.trim();
          await this.plugin.saveSettings();
          this.plugin.refreshAdapter();
        });
      });

    // --- pythonBin --------------------------------------------------------
    new Setting(containerEl)
      .setName("Python binary")
      .setDesc("Absolute path to the python interpreter inside WSL, e.g. /home/u/.venvs/ormb/bin/python.")
      .addText((t) => {
        t.setValue(this.plugin.settings.pythonBin);
        t.onChange(async (v) => {
          this.plugin.settings.pythonBin = v.trim();
          await this.plugin.saveSettings();
          this.plugin.refreshAdapter();
        });
      });

    // --- rmFolder ---------------------------------------------------------
    new Setting(containerEl)
      .setName("reMarkable folder")
      .setDesc("Destination folder on reMarkable. Free text (allowlist validated by the CLI).")
      .addText((t) => {
        t.setValue(this.plugin.settings.rmFolder);
        t.onChange(async (v) => {
          this.plugin.settings.rmFolder = v.trim();
          await this.plugin.saveSettings();
        });
      });

    // --- visionModel ------------------------------------------------------
    new Setting(containerEl)
      .setName("Vision model")
      .setDesc("OpenRouter vision model slug for annotation transcription (pull). Leave empty for the CLI default.")
      .addText((t) => {
        t.setValue(this.plugin.settings.visionModel);
        t.onChange(async (v) => {
          this.plugin.settings.visionModel = v.trim();
          await this.plugin.saveSettings();
          this.plugin.refreshAdapter();
        });
      });

    // --- Test connection --------------------------------------------------
    new Setting(containerEl)
      .setName("Test connection")
      .setDesc("Run `ormb doctor` and render the status grid below.")
      .addButton((btn) => {
        btn.setButtonText("Test connection").onClick(async () => {
          btn.setButtonText("Testing…");
          btn.setDisabled(true);
          try {
            const doc = await this.plugin.adapter.doctor();
            renderStatusGrid(this.statusHost, doc);
            if (doc.ok && doc.errors.length === 0) {
              new Notice("ormb: all checks passed ✓");
            } else {
              new Notice("ormb: some checks failed — see settings.");
            }
          } catch (err) {
            new Notice(`Test connection failed: ${(err as Error).message}`);
          } finally {
            btn.setButtonText("Test connection");
            btn.setDisabled(false);
          }
        });
      });

    containerEl.appendChild(this.statusHost);

    // --- Copyable terminal commands --------------------------------------
    containerEl.createEl("h3", { text: "Terminal setup commands" });
    containerEl.createEl("p", {
      text: "Run these in your WSL terminal. The plugin cannot perform these (they need a TTY / sudo).",
      cls: "setting-item-description",
    });
    for (const c of COPYABLE_COMMANDS) {
      const setting = new Setting(containerEl).setName(c.label).setDesc(c.command);
      setting.addButton((btn) => {
        btn.setButtonText("Copy").onClick(async () => {
          try {
            await navigator.clipboard.writeText(c.command);
            new Notice(`Copied: ${c.command}`);
          } catch {
            new Notice("Copy failed — select the command manually.");
          }
        });
      });
    }
  }
}
