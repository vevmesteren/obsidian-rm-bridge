# T-WIN Install — Obsidian on Windows, ormb CLI native (no WSL)

## Prerequisites

- Windows 10/11
- Python 3.10+ (installed natively on Windows, added to PATH)
- Node.js 18+ (for building the plugin)
- Obsidian desktop
- A reMarkable account

## 1. Install the CLI (in PowerShell or Git Bash)

```powershell
# Clone the repo
git clone https://github.com/vevmesteren/obsidian-rm-bridge.git
cd obsidian-rm-bridge

# Create a venv and install
python -m venv .venv
.\.venv\Scripts\activate
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
# In Git Bash, or use the WSL path if you have WSL available
./scripts/install-plugin.sh 'C:\dev\MyVault'
```

Or from PowerShell:

```powershell
# Build
cd plugin
npm install
npm run build

# Copy manually (native Windows)
$vault = "C:\dev\MyVault"
$dest = "$vault\.obsidian\plugins\obsidian-rm-bridge"
New-Item -ItemType Directory -Force -Path $dest
Copy-Item main.js $dest
Copy-Item manifest.json $dest
```

## 3. Enable in Obsidian

1. Open Obsidian → Settings → Community plugins → enable "Obsidian reMarkable Bridge"
2. Plugin settings tab:
   - **Python binary**: `C:\dev\obsidian-rm-bridge\.venv\Scripts\python.exe`
   - **Topology**: Auto-detect (should resolve to Windows native)
3. Click "Test connection"

## Data egress disclosure

Same as T-WSL — see [T-WSL](INSTALL-T-WSL.md#data-egress-disclosure).