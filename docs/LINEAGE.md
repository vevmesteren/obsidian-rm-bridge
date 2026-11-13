# Lineage

[LINEAGE_COMPLETE]

## Origin

`obsidian-rm-bridge` is the open-source extraction of the **veviki-remarkable-bridge** — a Hermes Agent skill built by Valentin Backofen (vevmesteren) in November 2026.

## Skill Phases

| Phase | Date | What | Status |
|-------|------|------|--------|
| 1 | 2026-11-12 | `publish.py` — markdown → PDF → reMarkable upload | ✅ PoC proven |
| 2 | 2026-11-12 | `retrieve.py` — annotation round-trip via GLM-4.5V | ✅ PoC proven |
| 3 | 2026-11-12 | Polish: tests, CSS, folder publish, re-upload handling | ✅ Done |
| 4 | 2026-11-12 | Open source extraction (this repo) | ✅ Done — [PR #2](https://github.com/vevmesteren/obsidian-rm-bridge/pull/2), E2E verified on WSL |
| 5 | 2026-11-13 | Obsidian TypeScript plugin (thin CLI wrapper) | 🔄 In progress — [ARB](docs/ARB-OBSIDIAN-PLUGIN.md) synthesized, 5a-0 merged, 5a next |

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

## Phase 5 — Obsidian Plugin (ARB-Driven)

**ARB:** [`docs/ARB-OBSIDIAN-PLUGIN.md`](docs/ARB-OBSIDIAN-PLUGIN.md) — Synthesized target architecture (5-stage ARB pipeline,completed 2026-11-13)

**Delivery plan (from ARB):**

| Sub-phase | Scope | Status |
|-----------|-------|--------|
| 5a-0 | CLI contract changes (~150-250 LOC Python) | ✅ Done — [PR #8](https://github.com/vevmesteren/obsidian-rm-bridge/pull/8), 147 tests |
| 5a | Plugin scaffold + publish command (T-WSL) | Planned |
| 5b | Pull command + marker blocks | Planned |
| 5c | Native adapters + README + community store submission | Planned |
| 5d/v2 | PyPI release, Electron render spike | Deferred |

**Launch posture:** T-WSL is the only topology proven at v1 launch. T-MAC, T-LINUX, and T-WIN are community-tested via Reddit outreach + PRs.

## Original Plan Document

See `veviki-valentin/concepts/research/veviki-remarkable-bridge/veviki-remarkable-bridge-plan.md` for the original 5-phase plan.