# Contributing

> **Audience:** Developers who want to contribute to reMarkable Roundtrip

← Back to [README](../README.md)

Thanks for your interest in contributing! This plugin is a thin TypeScript
wrapper around a Python CLI (`ormb`), so contributions span both sides.

## Development setup

```bash
git clone https://github.com/vevmesteren/remarkable-roundtrip.git
cd remarkable-roundtrip

# Python CLI (with dev dependencies)
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Install Playwright Chromium
ormb setup

# Install rmapi (for E2E tests)
ormb setup --rmapi

# TypeScript plugin
cd plugin
npm install
npm run build
```

## Running tests

### Python tests

```bash
# From repo root, venv activated
pytest                    # all tests
pytest tests/ -v          # verbose
pytest --tb=short         # short tracebacks
pytest -k "publish"       # only publish tests
```

### TypeScript tests

```bash
cd plugin
npm test                  # all TS tests
npm run test:unit         # unit tests only
```

### E2E tests

E2E tests require a real reMarkable device and OpenRouter API key. See
[docs/T-WSL-TEST-PLAYBOOK.md](docs/T-WSL-TEST-PLAYBOOK.md) for the full
operator test playbook.

## Project structure

```
remarkable-roundtrip/
├── obsidian_rm_bridge/     # Python CLI package (ormb)
│   ├── cli.py              # Click CLI entry point
│   ├── config.py           # TOML config + env var overrides
│   ├── publisher.py        # markdown → PDF → rmapi upload
│   ├── retriever.py        # rmapi download → PNG → vision → append
│   ├── vision_client.py    # OpenRouter vision API client
│   ├── rmapi_client.py     # rmapi subprocess wrapper
│   └── ...
├── plugin/                 # TypeScript Obsidian plugin
│   ├── src/
│   │   ├── main.ts         # Plugin entry (commands, ribbon, settings)
│   │   ├── settings.ts     # Settings tab UI
│   │   ├── wsl-adapter.ts  # WSL path translation + process spawning
│   │   └── path-translate.ts
│   ├── manifest.json       # Obsidian plugin manifest
│   └── esbuild.config.mjs
├── docs/                   # Documentation
├── scripts/                # Install + release scripts
├── tests/                  # Python tests
└── pyproject.toml          # Python package config
```

## PR conventions

1. **Branch naming:** `feature/<topic>`, `fix/<topic>`, or `opencode/<phase>-<topic>`
2. **Commit messages:** conventional commits (`feat:`, `fix:`, `docs:`, `test:`)
3. **CI must pass** — both Python (`ci.yml`: ruff + pytest) and TypeScript (`plugin-ci.yml`: build + banned-pattern grep)
4. **Banned patterns in `plugin/src/`:** `exec(`, `execSync(`, `shell: true`, `bash -c`, `cmd.exe /c` — the plugin must never invoke a shell when spawning `ormb`
5. **Add tests** for new functionality
6. **Update docs** if you change user-facing behavior

## CI checks

| Workflow | What it checks |
|----------|---------------|
| `ci.yml` | Python: ruff lint, pytest (all tests must pass) |
| `plugin-ci.yml` | TypeScript: esbuild build, banned-pattern grep in `plugin/src/` |

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full system
architecture, C4 diagrams, and design contracts (DC-1 through DC-10).

The plugin is deliberately a **thin wrapper** — it spawns `ormb` via
`child_process` (no shell), parses JSON output, and writes to the vault. All
business logic lives in the Python CLI.

← Back to [README](../README.md)
