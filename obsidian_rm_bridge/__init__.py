"""obsidian-rm-bridge — Publish Obsidian markdown to reMarkable, pull handwritten annotations back.

A Python package that does the full Obsidian → reMarkable → Obsidian round-trip:
publish markdown pages (with mermaid diagrams) to reMarkable as PDFs via Playwright,
then retrieve handwritten annotations transcribed by a vision LLM back into the vault.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]