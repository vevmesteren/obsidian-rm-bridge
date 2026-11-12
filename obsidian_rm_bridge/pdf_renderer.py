"""HTML → PDF via Playwright (DC-1).

Replaces weasyprint. Chromium's ``page.pdf()`` produces a print-formatted PDF
with no GTK/Pango dependency, identically on Mac, Windows, and Linux.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["html_to_pdf", "page_count"]


def html_to_pdf(
    html: str,
    pdf_path: str | Path,
    *,
    title: str = "obsidian-rm-bridge",
    timeout_ms: int = 60_000,
) -> str:
    """Render a full HTML document to ``pdf_path`` via headless Chromium.

    The HTML may embed mermaid PNGs as base64 data URLs (self-contained).
    Returns ``pdf_path``.
    """
    from playwright.sync_api import sync_playwright

    out = Path(pdf_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="networkidle", timeout=timeout_ms)
            page.emulate_media(media="print")
            page.pdf(
                path=str(out),
                format="A4",
                print_background=True,
                margin={"top": "18mm", "bottom": "18mm", "left": "16mm", "right": "16mm"},
            )
        finally:
            browser.close()
    return str(out)


def page_count(pdf_path: str | Path) -> int:
    """Best-effort page count via pymupdf; returns ``-1`` if unavailable."""
    try:
        import fitz

        doc = fitz.open(str(pdf_path))
        n = doc.page_count
        doc.close()
        return n
    except Exception:  # noqa: BLE001 - best-effort page count
        return -1