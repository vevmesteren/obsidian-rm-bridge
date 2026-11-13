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
  mermaid.initialize({{ startOnLoad: true, securityLevel: 'strict', theme: 'default', htmlLabels: false }});
</script>
</body></html>"""


def _make_route_handler(vault_root: Path | None = None):
    """Build a Playwright route interceptor that only allows safe resources.

    Allows: ``data:`` URIs, the mermaid CDN script, and in-vault ``file:``
    URIs (containment-checked). Everything else is aborted (ARB item 8).

    When ``vault_root`` is ``None``, ALL ``file://`` URIs are blocked (there
    is no vault to contain against) — only ``data:`` and the mermaid CDN URL
    are allowed.
    """
    def _handler(route, request):
        url = request.url
        if url.startswith("data:"):
            route.continue_()
            return
        if url.startswith(MERMAID_JS_URL):
            route.continue_()
            return
        if url.startswith("file://") and vault_root is not None:
            from urllib.parse import urlparse, unquote

            parsed = urlparse(url)
            local = Path(unquote(parsed.path))
            try:
                resolved = local.resolve()
            except Exception:  # noqa: BLE001
                route.abort()
                return
            if resolved.is_relative_to(vault_root.resolve()):
                route.continue_()
                return
            route.abort()
            return
        # Block everything else
        route.abort()
    return _handler


def render_mermaid_to_png(
    diagram: str,
    output_path: str | Path,
    *,
    width: int = MERMAID_WIDTH,
    timeout_ms: int = 30_000,
    vault_root: str | Path | None = None,
) -> str:
    """Render a single mermaid ``diagram`` to ``output_path`` (PNG).

    Raises ``RuntimeError`` if Playwright cannot render the diagram in time.
    """
    from playwright.sync_api import sync_playwright

    html = _HTML_TEMPLATE.format(url=MERMAID_JS_URL, diagram=diagram)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    vr = Path(str(vault_root)).resolve() if vault_root is not None else None

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": 800})
            # ARB item 8: the route interceptor must ALWAYS be active, even when
            # vault_root is None (e.g. render_mermaid_blocks default path).
            # When vault_root is None, file:// URIs are blocked unconditionally
            # (no vault to contain against) and only data: and the mermaid CDN
            # URL are allowed.
            page.route("**/*", _make_route_handler(vr))
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


def render_mermaid_blocks(content: str, *, workdir: str | Path | None = None,
                          vault_root: str | Path | None = None) -> str:
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
                render_mermaid_to_png(block, png_path, vault_root=vault_root)
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