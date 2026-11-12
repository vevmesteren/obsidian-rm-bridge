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

### Install

```bash
pip install obsidian-rm-bridge
ormb setup          # installs Playwright browser
ormb setup --rmapi  # downloads rmapi binary

# Pair with reMarkable (one-time)
ormb pair

# Configure your vault path
ormb config set vault_path ~/Documents/Obsidian
```

### Publish to reMarkable (no API key needed)

```bash
# Publish a single page
ormb publish my-research-notes.md

# Publish all .md files in a folder as one combined PDF
ormb publish my-project/ --folder
```

That's it — your page is on your reMarkable, ready to annotate.

### Pull annotations back (requires OpenRouter API key)

Annotation transcription uses a vision LLM via [OpenRouter](https://openrouter.ai). You'll need an OpenRouter account and API key.

```bash
# Set your API key
ormb config set openrouter_api_key sk-or-v1-xxx

# Pull handwritten annotations back into the source markdown file
ormb pull my-research-notes
```

Annotations are appended as:

```markdown
## Annotations from reMarkable — 2026-11-12

**Page 1:**
> your handwritten notes transcribed here
```

## Installation

### Prerequisites

| Dependency | Mac | Windows | Linux |
|------------|-----|---------|-------|
| Python 3.10+ | `brew install python` | [python.org](https://python.org) | `apt install python3 python3-pip` |
| rmapi | `ormb setup --rmapi` | Same | Same |

### macOS

```bash
brew install python
pip install obsidian-rm-bridge
ormb setup
ormb setup --rmapi
```

### Windows

```bash
# Install Python 3.10+ from python.org (check "Add to PATH")
pip install obsidian-rm-bridge
ormb setup
ormb setup --rmapi

# Or use WSL (full Linux environment):
wsl --install -d Ubuntu
# Then follow Linux instructions inside WSL
```

### Linux

```bash
sudo apt install python3 python3-pip
pip install obsidian-rm-bridge
ormb setup
ormb setup --rmapi
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `ormb publish <file>` | Publish a single markdown page to reMarkable |
| `ormb publish <folder> --folder` | Publish all .md files as a combined PDF |
| `ormb pull <page-name>` | Download, transcribe annotations, append to source .md |
| `ormb pull --all` | Pull all annotated pages from your reMarkable folder |
| `ormb ls` | List files on reMarkable |
| `ormb rm <page-name>` | Delete a file on reMarkable |
| `ormb config set <key> <value>` | Set a configuration option |
| `ormb config show` | Show current configuration |
| `ormb pair` | Pair with reMarkable (prompts for one-time code) |
| `ormb setup` | Install Playwright browser |
| `ormb setup --rmapi` | Download and install rmapi binary |

## Configuration

Config lives at `~/.obsidian-rm-bridge/config.toml`. Environment variables override file values.

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
```

## How Annotation Transcription Works

1. After annotating on your reMarkable, run `ormb pull`
2. The annotated PDF is downloaded via rmapi
3. Each page is rendered to PNG at 300 DPI
4. Pages are sent to a vision-capable LLM (GLM-4.5V by default)
5. Handwritten annotations are transcribed to text
6. Optionally cross-verified with a second model (GPT-4o)
7. Transcribed annotations are appended to your source markdown file

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full architecture breakdown and [docs/LINEAGE.md](docs/LINEAGE.md) for project history.

## License

MIT
