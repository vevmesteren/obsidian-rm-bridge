# Lineage

## Origin

`obsidian-rm-bridge` is the open-source extraction of the **veviki-remarkable-bridge** — a Hermes Agent skill built by Valentin Backofen (vevmesteren) in November 2026.

## Skill Phases

| Phase | Date | What | Status |
|-------|------|------|--------|
| 1 | 2026-11-12 | `publish.py` — markdown → PDF → reMarkable upload | ✅ PoC proven |
| 2 | 2026-11-12 | `retrieve.py` — annotation round-trip via GLM-4.5V | ✅ PoC proven |
| 3 | 2026-11-12 | Polish: tests, CSS, folder publish, re-upload handling | ✅ Done |
| **4** | **2026-11-12** | **Open source extraction** (this repo) | **In progress** |
| 5 | TBD | Obsidian TypeScript plugin (thin CLI wrapper) | Planned |

## Source Files

The original skill code lives at:
```
~/.hermes/profiles/vevmesteren/skills/productivity/veviki-remarkable-bridge/
├── SKILL.md           # Skill documentation
├── publish.py         # 365 lines — publish pipeline
├── retrieve.py        # 283 lines — retrieve pipeline
├── test_publish.py    # Tests (mocked rmapi)
└── test_retrieve.py   # Tests (mocked rmapi + vision API)
```

## Key Changes in Open-Source Extraction

1. **weasyprint → Playwright** — eliminates GTK/Pango Windows install nightmare, also replaces mmdc for mermaid rendering
2. **Hardcoded paths → configurable** — no veviki or Hermes coupling
3. **Script files → pip package** — `pip install obsidian-rm-bridge`, CLI `ormb`
4. **Hardcoded model → configurable** — default GLM-4.5V, any OpenRouter model
5. **Single-purpose → cross-platform** — Mac, Windows, Linux install paths documented

## Original Plan Document

See `veviki-valentin/concepts/research/veviki-remarkable-bridge/veviki-remarkable-bridge-plan.md` for the original 5-phase plan.
