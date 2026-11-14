# T-WSL Install — Obsidian on Windows, ormb CLI in WSL2

## Prerequisites

- Windows 10/11 with WSL2 (Ubuntu recommended)
- Python 3.10+ in WSL
- Node.js 18+ (for building the plugin — can be in WSL or Windows)
- Obsidian desktop on Windows
- A reMarkable account (for rmapi pairing)

## 1. Install the CLI (in WSL)

```bash
# Clone the repo
git clone https://github.com/vevmesteren/obsidian-rm-bridge.git
cd obsidian-rm-bridge

# Create a venv and install
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Install Chromium for Playwright
ormb setup

# Install rmapi binary (pinned, SHA-256 verified)
ormb setup --rmapi

# Pair reMarkable Cloud
ormb pair

# Set your OpenRouter API key (for vision transcription on pull)
ormb config set-key

# Verify
ormb doctor --json
```

`ormb doctor` should show `"ok": true`, `"paired": true`, `"key_present": true`.

## 2. Build and install the plugin

```bash
# From the repo root in WSL
./scripts/install-plugin.sh /mnt/c/dev/veviki
```

Replace `/mnt/c/dev/veviki` with your Obsidian vault path (WSL-style: `/mnt/c/...`).

The script:
- Runs `npm install` + `npm run build` in `plugin/`
- Copies `main.js` + `manifest.json` to `<vault>/.obsidian/plugins/obsidian-rm-bridge/`

## 3. Enable in Obsidian

1. Open Obsidian → Settings → Community plugins
2. Find "Obsidian reMarkable Bridge" → enable it
3. Open the plugin settings tab → set:
   - **Python binary**: `/mnt/c/dev/obsidian-rm-bridge/.venv/bin/python` (adjust to your repo path)
   - **Topology**: Auto-detect (should resolve to WSL)
4. Click "Test connection" — all checks should pass

## 4. Usage

- **Publish**: Open a note → `Ctrl+P` → "Publish to reMarkable"
- **Pull**: `Ctrl+P` → "Pull annotations from reMarkable" (first run shows consent modal)

## Data egress disclosure

- **Publish**: markdown → PDF → uploaded to reMarkable Cloud via rmapi. No OpenRouter.
- **Pull**: annotated PDF pages → rendered to PNG → sent to OpenRouter vision model for transcription. Cached by PDF hash + model — re-pulling unchanged content does NOT call OpenRouter.