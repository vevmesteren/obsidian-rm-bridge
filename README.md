# obsidian-rm-bridge

> Publish Obsidian markdown pages to your reMarkable tablet as PDFs, annotate by hand, then pull handwriting back into your vault as structured text.

The only reMarkable ↔ Obsidian tool that does the **full round-trip**.

## How It Works

```
Obsidian .md  →  PDF (with mermaid diagrams)  →  reMarkable
                                                     ↓
                                               annotate by hand
                                                     ↓
Obsidian .md  ←  transcribed text (vision LLM)  ←  reMarkable
```

## Quick Start

### Install from source (recommended until PyPI release)

```bash
git clone https://github.com/vevmesteren/obsidian-rm-bridge.git
cd obsidian-rm-bridge

# Use a venv (avoids system Python permission issues)
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .
playwright install chromium      # needed for PDF rendering

ormb setup --rmapi               # downloads rmapi binary for your platform
ormb setup                       # installs Chromium + system deps (Linux needs sudo)

# Pair with reMarkable (one-time)
ormb pair

# Configure your vault path
ormb config set vault.path ~/Documents/Obsidian
```

<!-- Once published to PyPI, the above can be replaced with `pip install obsidian-rm-bridge` -->

> **WSL/Ubuntu users:** If `python3 -m venv .venv` fails with "ensurepip not available",
> install the venv package for your Python version, e.g. `sudo apt install python3.10-venv`,
> then recreate the venv.

### Publish to reMarkable (no API key needed)

```bash
# Publish a single page (relative paths resolve against vault.path)
ormb publish my-research-notes.md
ormb publish concepts/architecture/c4-system-landscape.md

# Or use an absolute path
ormb publish /path/to/any-note.md

# Publish all .md files in a folder as one combined PDF
ormb publish my-project/ --folder
```

That's it — your page is on your reMarkable, ready to annotate.

### Pull annotations back (requires OpenRouter API key)

Annotation transcription uses a vision LLM via [OpenRouter](https://openrouter.ai). You'll need an OpenRouter account and API key.

```bash
# Set your API key (reads from stdin — key not visible in argv)
echo sk-or-v1-your-key-here | ormb config set-key

# List what's on your reMarkable to find the page name
ormb ls

# Pull annotations — the page name is the reMarkable document name
# (the .md file stem from publish, e.g. "c4-system-landscape")
ormb pull c4-system-landscape

# If the source .md is in a subdirectory, use --md to specify it:
ormb pull c4-system-landscape --md concepts/architecture/c4-system-landscape.md

# Or pull all annotated pages from your reMarkable folder:
ormb pull --all

# Get the page count WITHOUT calling vision (for the consent modal):
ormb pull my-page --info --json
```

Annotations are appended as a single date-titled section with one bullet per
annotation:

```markdown
## [2026-11-13] Annotations

- handwritten annotation text
- another annotation
```

> **Caching:** re-pulling an unchanged document hits a local cache (keyed by
> the PDF content hash) and skips the paid vision pipeline. If the
> annotations change, the PDF hash changes and the cache misses, so it
> re-transcribes.

## Installation

### Prerequisites

| Dependency | Mac | Windows | Linux |
|------------|-----|---------|-------|
| Python 3.10+ | `brew install python` | [python.org](https://python.org) | `apt install python3 python3-pip` |
| rmapi | `ormb setup --rmapi` | Same | Same |

### macOS

```bash
brew install python
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
ormb setup --rmapi
```

### Windows

```powershell
# Install Python 3.10+ from python.org (check "Add to PATH")
python -m venv .venv
.venv\Scripts\activate
pip install -e .
ormb setup --rmapi

# Or use WSL (full Linux environment):
wsl --install -d Ubuntu
# Then follow Linux instructions inside WSL
```

### Linux

```bash
# Install Python + venv support (venv package is separate on Debian/Ubuntu)
sudo apt install python3 python3-pip python3-venv python3.10-venv
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
ormb setup --rmapi
ormb setup          # installs Chromium + system libs (libgbm, libnss, etc.)
                    # runs `sudo playwright install-deps` automatically
```

## Topologies

The bridge has been validated across four host/topology combinations. Pick
the one that matches where Obsidian runs.

| Topology | Obsidian on | CLI / venv / rmapi | Status |
|----------|------------|-------------------|-------|
| T-WSL | Windows | WSL2 Ubuntu | Primary, E2E-tested |
| T-MAC | macOS | Native venv | Community-tested |
| T-LINUX | Linux desktop | Native venv + rmapi | Community-tested |
| T-WIN | Windows | Native Windows Python | Secondary, community-tested |

### T-WSL — Windows + WSL2 Ubuntu (primary)

Obsidian runs on Windows; the CLI, venv, and rmapi live inside a WSL2 Ubuntu
distribution. This is the primary, end-to-end-tested topology.

```powershell
# Windows side
wsl --install -d Ubuntu
# Inside WSL Ubuntu:
sudo apt install python3 python3-pip python3-venv python3.10-venv
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
ormb setup --rmapi
ormb setup
ormb pair
ormb config set vault.path /mnt/c/Users/<you>/Documents/Obsidian
```

The vault path points at the Windows filesystem mounted under `/mnt/c`.

### T-MAC — macOS native

Obsidian and the CLI both run natively on macOS.

```bash
brew install python
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
ormb setup --rmapi
ormb pair
ormb config set vault.path ~/Documents/Obsidian
```

### T-LINUX — Linux desktop native

Obsidian and the CLI both run on a Linux desktop.

```bash
sudo apt install python3 python3-pip python3-venv python3.10-venv
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
ormb setup --rmapi
ormb setup
ormb pair
ormb config set vault.path ~/Documents/Obsidian
```

### T-WIN — Windows native Python

The CLI runs under native Windows Python (no WSL). Obsidian runs on Windows.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e .
ormb setup --rmapi
ormb config set vault.path C:\Users\<you>\Documents\Obsidian
```

> Playwright Chromium on native Windows generally does not need the
> `install-deps` step (that's Linux-only).

## Obsidian Plugin

The companion Obsidian plugin is a thin TypeScript wrapper that spawns the
`ormb` CLI via `child_process`. It adds **Publish** and **Pull** commands to
Obsidian's command palette and a settings tab.

### Install

Once accepted into the community plugin store, you can install it directly
from Obsidian:

1. **Settings → Community plugins → Browse** and search for
   "Obsidian reMarkable Bridge".
2. Click **Install**, then **Enable**.

Until then, install from source with the install script:

```bash
# From the repo root — builds the plugin and copies it to your vault
./scripts/install-plugin.sh <vault-path>
# e.g. ./scripts/install-plugin.sh /mnt/c/dev/veviki
# e.g. ./scripts/install-plugin.sh ~/Documents/Obsidian
# e.g. ./scripts/install-plugin.sh 'C:\dev\MyVault'
```

The script runs `npm run build` and copies `main.js` + `manifest.json` into
`<vault>/.obsidian/plugins/obsidian-rm-bridge/`. It handles WSL paths
(`/mnt/c/...`) and Windows paths (`C:\...`) automatically.

For step-by-step per-topology instructions, see:

- **[T-WSL](docs/INSTALL-T-WSL.md)** — Obsidian on Windows, CLI in WSL2 (primary)
- **[T-MAC](docs/INSTALL-T-MAC.md)** — Obsidian on macOS, native CLI
- **[T-LINUX](docs/INSTALL-T-LINUX.md)** — Obsidian on Linux, native CLI
- **[T-WIN](docs/INSTALL-T-WIN.md)** — Obsidian on Windows, native CLI (no WSL)

After installing:

1. In Obsidian: **Settings → Community plugins** → enable "Obsidian reMarkable Bridge"
2. Open the plugin settings tab → set the **Python binary** path
3. Click **Test connection** — all checks should pass

### Usage

The plugin adds two commands to the command palette (`Ctrl/Cmd+P`):

- **Publish current note to reMarkable** — renders the active note to PDF and
  uploads it. Assigns the document the note's stem as its name.
- **Pull annotations from reMarkable** — downloads the annotated PDF for the
  current note's name, shows a **consent modal** with the page count that will
  be sent to OpenRouter, and (after consent) transcribes the handwriting back
  into the note as a date-titled annotation section.

The first pull triggers a **consent dialog** because page images are sent to
OpenRouter for vision transcription. The plugin shows the page count (via
`ormb pull --info`) before you consent to the cost.

### Settings tab

The plugin settings tab lets you:

- **Test connection** — verifies `ormb` is on PATH and reports the doctor
  health check.
- Run the **terminal setup commands** (`ormb setup --rmapi`, `ormb pair`,
  `ormb config set-key`) with copy-to-clipboard buttons so you can run them
  in a real terminal (the plugin does not capture your API key).

### Screenshots

![Publish command](docs/screenshots/publish.png)

![Pull command](docs/screenshots/pull.png)

> The operator fills in these screenshots during the E2E test pass before the
> community-store submission.

## CLI Reference

| Command | Description |
|---------|-------------|
| `ormb publish <file>` | Publish a single markdown page to reMarkable |
| `ormb publish <folder> --folder` | Publish all .md files as a combined PDF |
| `ormb pull <page-name>` | Pull annotations from reMarkable (page-name = .md stem, e.g. `c4-system-landscape`) |
| `ormb pull <page-name> --md <path>` | Same, but specify the source .md file (for subdirectory notes) |
| `ormb pull <page-name> --info --json` | Get page count without calling vision (for the consent modal) |
| `ormb pull --all` | Pull all annotated pages from your reMarkable folder |
| `ormb ls` | List files on reMarkable |
| `ormb rm <page-name>` | Delete a file on reMarkable |
| `ormb config set <key> <value>` | Set a configuration option |
| `ormb config set-key` | Set the OpenRouter API key from stdin (not visible in argv) |
| `ormb config show` | Show current configuration |
| `ormb pair` | Pair with reMarkable (prompts for one-time code) |
| `ormb setup` | Install Playwright browser |
| `ormb setup --rmapi` | Download and install rmapi binary (version-pinned, sha256-verified) |
| `ormb doctor` | Health check for dependencies and configuration |

## Configuration

Config lives at `~/.obsidian-rm-bridge/config.toml`. Environment variables
override file values.

```toml
[vault]
path = "~/Documents/Obsidian"

[remarkable]
folder = "/Obsidian"

[vision]
model = "z-ai/glm-4.5v"
cross_verify_model = "gpt-4o"
openrouter_api_key = ""

[pdf]
font_size = 14
font_family = "Georgia"
code_font_size = 12

[render]
sanitize_html = true       # strip raw <script>/on* HTML before PDF render
resolve_wikilinks = true    # convert [[note]] to display text
```

Environment variable overrides: `ORB_VAULT_PATH`, `ORB_RM_FOLDER`,
`ORB_VISION_MODEL`, `ORB_VISION_CROSS_VERIFY_MODEL`, `OPENROUTER_API_KEY`,
`ORB_PDF_FONT_SIZE`, `ORB_PDF_FONT_FAMILY`, `ORB_PDF_CODE_FONT_SIZE`,
`ORB_SANITIZE_HTML`, `ORB_RESOLVE_WIKILINKS`.

## How Annotation Transcription Works

1. After annotating on your reMarkable, run `ormb pull`
2. The annotated PDF is downloaded via rmapi
3. Each page is rendered to PNG at 300 DPI
4. Pages are sent to a vision-capable LLM (GLM-4.5V by default)
5. Handwritten annotations are transcribed to text
6. Optionally cross-verified with a second model (GPT-4o)
7. Transcribed annotations are appended to your source markdown file

## Security & Data Egress Disclosures

This tool moves data between your machine, the reMarkable Cloud, and an
external LLM provider. Please review these egress points before use.

- **reMarkable Cloud egress (publish + pull):** when you `ormb publish`, the
  rendered PDF is uploaded to the reMarkable Cloud via `rmapi` (the unofficial
  Go client). When you `ormb pull`, the annotated PDF is downloaded from the
  reMarkable Cloud via `rmapi`. Your markdown content transits reMarkable's
  servers.
- **OpenRouter egress (pull only):** when you `ormb pull`, each page is
  rendered to a PNG image and sent to [OpenRouter](https://openrouter.ai) for
  vision transcription. The images and the returned transcribed text transit
  OpenRouter and the underlying model provider. The first pull shows a
  **consent modal** (plugin) / requires you to run the command explicitly
  (CLI) — no pull happens automatically. You need an OpenRouter API key, set
  via `ormb config set-key`.
- **External binary execution:** the Obsidian plugin spawns `ormb` (the
  Python CLI), which in turn spawns **Chromium** (via Playwright, for
  markdown→PDF and mermaid rendering) and **`rmapi`** (a third-party Go binary
  downloaded from `ddvk/rmapi` releases, version-pinned and sha256-verified).
  The plugin never invokes a shell (`shell: true` is banned in `plugin/src/`
  and enforced by CI).
- **HTML sanitisation:** raw HTML embedded in a note (e.g. `<script>` or
  `on*` event handlers) is stripped via [bleach](https://github.com/mozilla/bleach)
  before the PDF render, so it cannot reach Playwright/Chromium. This is on
  by default (`render.sanitize_html = true`); disable it only if you trust
  your vault's contents.
- **Local pull cache:** `ormb pull` caches vision results by PDF content hash
  at `~/.obsidian-rm-bridge/pull_cache.json` so re-pulling an unchanged
  document does not re-pay OpenRouter. The cache contains transcribed text; no
  images are stored.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full architecture
breakdown and [docs/LINEAGE.md](docs/LINEAGE.md) for project history.

## License

MIT
