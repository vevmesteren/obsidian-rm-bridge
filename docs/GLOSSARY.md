# Glossary

> **Audience:** All users — especially newcomers to the Obsidian + reMarkable ecosystem

← Back to [README](../README.md)

| Term | Definition |
|------|-----------|
| **ormb** | The CLI for obsidian-rm-bridge. Short for "reMarkable Roundtrip." |
| **rmapi** | A third-party Go binary ([ddvk/rmapi](https://github.com/ddvk/rmapi)) that communicates with the reMarkable Cloud API. Used for uploading PDFs and downloading annotated documents. |
| **Playwright** | A browser automation library (by Microsoft) that drives Chromium. obsidian-rm-bridge uses it to render markdown → PDF (including mermaid diagrams) without a GUI. |
| **OpenRouter** | An API aggregator for LLMs. obsidian-rm-bridge uses it to access vision-capable models (like GLM-4.5V) for handwriting transcription. |
| **GLM-4.5V** | The default vision model used for transcription. A multimodal LLM available via OpenRouter. |
| **Topology** | A specific combination of where Obsidian runs and where the CLI/venv/rmapi live. Four topologies are supported: T-WSL, T-MAC, T-LINUX, T-WIN. |
| **T-WSL** | Topology: Obsidian on Windows, CLI in WSL2 Ubuntu. The primary, E2E-tested topology. |
| **T-MAC** | Topology: Obsidian and CLI both native on macOS. |
| **T-LINUX** | Topology: Obsidian and CLI both on a Linux desktop. |
| **T-WIN** | Topology: Obsidian and CLI both native on Windows (no WSL). |
| **Marker block** | An HTML comment (`<!-- ormb:annotations doc="..." rev="..." -->`) inserted into your note when annotations are pulled. It marks the boundary of the annotation section so subsequent pulls can replace it. Stripped from published PDFs. |
| **Vision LLM** | A large language model that can process images. Used to transcribe handwritten annotations from PNG page images. |
| **DC** | Design Contract. A binding architectural decision documented in [ARCHITECTURE.md](ARCHITECTURE.md). E.g., DC-7 = annotation format, DC-5 = rmapi refresh before geta. |
| **ARB** | Architecture Review Board. A 5-stage adversarial review pipeline used to design the Obsidian plugin. See [ARB-OBSIDIAN-PLUGIN.md](ARB-OBSIDIAN-PLUGIN.md). |
| **venv** | Python virtual environment. Isolates package dependencies from the system Python. Created with `python3 -m venv .venv`. |
| **pull cache** | A local JSON file (`~/.obsidian-rm-bridge/pull_cache.json`) that stores vision transcription results keyed by PDF content hash + model. Prevents re-paying for unchanged documents. |
| **consent modal** | A dialog in the Obsidian plugin that shows the page count and model before sending images to OpenRouter. Ensures informed consent before any cost is incurred. |
| `--on-exists` | A publish flag controlling overwrite behavior. `fail` (default) refuses to overwrite. `content-only` replaces only if content changed (preserves annotations). |

← Back to [README](../README.md)
