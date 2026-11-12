"""Render mermaid code blocks to PNG via Playwright (DC-1).

Replaces the mmdc CLI subprocess. A headless Chromium page loads mermaid.js
(pinned CDN version), renders each diagram, and screenshots the resulting SVG.
If a diagram fails to render, the block is left as-is in the output.
"""

from __future__ import annotations

import base64
import re
import tempfile
from pathlib import Path

__all__ = [
    "MERMAID_JS_URL",
    "MERMAID_WIDTH",
    "render_mermaid_blocks",
    "render_mermaid_to_png",
]

# Pinned mermaid.js version (risk register: pin to avoid incompatibility).
MERMAID_JS_URL = (
    "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"
)
MERMAID_WIDTH = 1200

_MERMAID_FENCE = r'```mermaid\r?\n(.*?)\r?\n```'

# Minimal HTML host that loads mermaid and renders one diagram into a container
# we can screenshot. ``waitUntil=networkidle`` ensures mermaid.js has loaded.
_HTML_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8">
<script src="{url}"></script>
<style>body{{margin:0;background:#fff;}} .mermaid{{background:#fff;}}</style>
</head><body>
<div class="mermaid">{diagram}</div>
<script>
  mermaid.initialize({{ startOnLoad: true, securityLevel: 'loose', theme: 'default' }});
</script>
</body></html>"""


def render_mermaid_to_png(
    diagram: str,
    output_path: str | Path,
    *,
    width: int = MERMAID_WIDTH,
    timeout_ms: int = 30_000,
) -> str:
    """Render a single mermaid ``diagram`` to ``output_path`` (PNG).

    Raises ``RuntimeError`` if Playwright cannot render the diagram in time.
    """
    from playwright.sync_api import sync_playwright

    html = _HTML_TEMPLATE.format(url=MERMAID_JS_URL, diagram=diagram)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": 800})
            page.set_content(html, wait_until="networkidle")
            # Wait for mermaid to swap the fenced code for an <svg>.
            page.wait_for_selector("svg", timeout=timeout_ms, state="attached")
            svg = page.query_selector("svg")
            if svg is None:  # pragma: no cover - selector guard
                raise RuntimeError("mermaid did not produce an <svg>")
            svg.screenshot(path=str(out))
        finally:
            browser.close()
    return str(out)


def render_mermaid_blocks(content: str, *, workdir: str | Path | None = None) -> str:
    """Replace ```` ```mermaid ```` code blocks with embedded PNG ``<img>`` tags.

    Each block is rendered via :func:`render_mermaid_to_png` and inlined as a
    base64 data URL so the resulting HTML/PDF is self-contained. Blocks that
    fail to render are left untouched.
    """
    blocks = re.findall(_MERMAID_FENCE, content, re.DOTALL)
    if not blocks:
        return content

    images: list[str | None] = []
    tmpdir = workdir or tempfile.mkdtemp(prefix="ormb-mermaid-")
    keep_tmp = workdir is not None
    try:
        for i, block in enumerate(blocks):
            png_path = Path(tmpdir) / f"diagram_{i}.png"
            try:
                render_mermaid_to_png(block, png_path)
                with png_path.open("rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                images.append(
                    f'<img src="data:image/png;base64,{b64}" '
                    f'style="max-width:100%;" alt="mermaid diagram {i}"/>'
                )
            except Exception:  # noqa: BLE001 - degrade gracefully on any render failure
                images.append(None)
    finally:
        if not keep_tmp:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)

    idx = [0]

    def _replace(match: re.Match) -> str:
        j = idx[0]
        idx[0] += 1
        img = images[j] if j < len(images) else None
        return img if img is not None else match.group(0)

    return re.sub(_MERMAID_FENCE, _replace, content, flags=re.DOTALL)