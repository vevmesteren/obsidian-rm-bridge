# T-MAC Install — Obsidian on macOS, ormb CLI native

## Prerequisites

- macOS 12+ (Apple Silicon or Intel)
- Python 3.10+
- Node.js 18+
- Obsidian desktop
- A reMarkable account

## 1. Install the CLI

```bash
git clone https://github.com/vevmesteren/obsidian-rm-bridge.git
cd obsidian-rm-bridge

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Install Chromium for Playwright
ormb setup

# Install rmapi (pinned, SHA-256 verified)
ormb setup --rmapi

# Pair reMarkable Cloud
ormb pair

# Set OpenRouter API key
ormb config set-key

# Verify
ormb doctor --json
```

## 2. Build and install the plugin

```bash
./scripts/install-plugin.sh /Users/you/MyVault
```

Replace the path with your Obsidian vault path.

## 3. Enable in Obsidian

1. Open Obsidian → Settings → Community plugins → enable "Obsidian reMarkable Bridge"
2. Plugin settings tab:
   - **Python binary**: `/Users/you/obsidian-rm-bridge/.venv/bin/python` (adjust path)
   - **Topology**: Auto-detect (should resolve to macOS)
3. Click "Test connection"

## Data egress disclosure

Same as T-WSL — see [T-WSL](INSTALL-T-WSL.md#data-egress-disclosure).