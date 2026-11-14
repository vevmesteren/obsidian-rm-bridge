"""Publish pipeline: markdown → mermaid PNG → HTML → PDF → reMarkable upload.

Refactored from the proven veviki-remarkable-bridge ``publish.py``:
- mermaid rendering via Playwright (was mmdc) — :mod:`mermaid_renderer` (DC-1)
- HTML→PDF via Playwright (was weasyprint) — :mod:`pdf_renderer` (DC-1)
- upload via :mod:`rmapi_client` (never ``--force``, DC-8)
No veviki or Hermes paths — all configuration comes from :mod:`config` (DC-3).
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

from . import rmapi_client
from .config import get
from .css import build_css
from .mermaid_renderer import render_mermaid_blocks
from .pdf_renderer import html_to_pdf, page_count
from .utils import list_md_files, strip_frontmatter, strip_marker_blocks

__all__ = [
    "folder_to_pdf",
    "md_to_html",
    "md_to_pdf",
    "publish_folder",
    "publish_page",
    "wrap_html",
]

# Match markdown image syntax: ![alt](relative/path.png)
_IMG_RE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
# Match Obsidian wiki-embed syntax: ![[image.png]]
_WIKI_EMBED_RE = re.compile(r'!\[\[([^\]]+)\]\]')
# Match Obsidian wikilinks: [[note]], [[note|alias]], [[note#heading]], [[note#heading|alias]]
_WIKILINK_RE = re.compile(r'\[\[([^\]]+)\]\]')


def _resolve_wikilinks(content: str) -> str:
    """Convert Obsidian wikilinks to their display text (Phase 5c AC-4).

    - ``[[note]]`` → ``note``
    - ``[[note|alias]]`` → ``alias``
    - ``[[note#heading]]`` → ``note``  (strip heading anchor)
    - ``[[note#heading|alias]]`` → ``alias``

    Wikilinks inside fenced code blocks (``` or ~~~) are left untouched so
    example syntax in code samples is preserved. Inline code (single
    backticks) is NOT excluded.
    """
    def _display(inner: str) -> str:
        # Take alias after '|' if present, else the whole target.
        target = inner.split("|", 1)
        chosen = target[1] if len(target) == 2 else target[0]
        # Strip the heading anchor (everything after '#') from the chosen part.
        return chosen.split("#", 1)[0]

    def _replace(match: re.Match) -> str:
        return _display(match.group(1))

    fence_re = re.compile(r"(```|~~~)")
    parts = fence_re.split(content)
    segments: list[str] = []
    in_code = False
    buf: list[str] = []
    for part in parts:
        if part in ("```", "~~~"):
            if not in_code:
                if buf:
                    segments.append("".join(buf))
                    buf = []
                in_code = True
                buf.append(part)
            else:
                buf.append(part)
                segments.append("".join(buf))
                buf = []
                in_code = False
        else:
            if in_code:
                buf.append(part)
            else:
                segments.append(_WIKILINK_RE.sub(_replace, part))
    if buf:
        segments.append("".join(buf))
    return "".join(segments)


# --- HTML sanitiser (Phase 5c AC-3) -------------------------------------------
# Allowlist of tags and attributes for bleach.clean(). Raw HTML embedded in a
# note (e.g. <script>, on* handlers) is stripped before the PDF render so it
# cannot reach Playwright/Chromium. ``class`` is allowed on every tag so the
# e-ink CSS (which targets classes like .page-break) keeps working.
_ALLOWED_TAGS = {
    "p", "h1", "h2", "h3", "h4", "h5", "h6", "em", "strong", "del", "code",
    "pre", "a", "ul", "ol", "li", "blockquote", "table", "thead", "tbody",
    "tr", "th", "td", "img", "br", "hr", "div", "span",
}
_ALLOWED_ATTRIBUTES: dict = {
    "a": ["href", "title", "class"],
    "img": ["src", "alt", "title", "class"],
    "*": ["class"],
}


def _sanitize_html(html: str) -> str:
    """Strip disallowed tags/attributes via bleach (Phase 5c AC-3)."""
    import bleach

    return bleach.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        strip=True,
    )


def _resolve_image_paths(content: str, base_dir: Path, vault_root: Path | None = None) -> str:
    """Resolve relative image paths to absolute file:// URIs (Copilot #6).

    Handles both standard markdown ``![alt](src)`` and Obsidian wiki-embed
    ``![[image.png]]`` syntax (adversarial review: wiki-embeds are Obsidian's
    default image syntax). Absolute paths and URLs are left unchanged.

    Standard markdown images are resolved against ``base_dir`` (the note's
    directory). Obsidian wiki-embeds are resolved against ``vault_root``
    (the vault root) when provided, because Obsidian resolves wiki links
    from the vault root by default (Copilot R3-3).

    Percent-encoded paths (``My%20diagram.png``) are decoded before resolving
    (Copilot R2-2). Obsidian wiki-embed size suffixes (``![[diagram.png|400]]``)
    are stripped before resolving (Copilot R2-3).
    """
    from urllib.parse import unquote

    def _split_code_blocks(text: str) -> list[tuple[str, bool]]:
        """Split text into (segment, is_code) pairs (Copilot R3-4).

        Fenced code blocks using ``` or ~~~ are marked as code so image
        resolution only applies to prose, not examples. Unterminated fences
        are treated as code to the end (adversarial M1). Tilde fences ~~~
        are handled (adversarial M2). Inline code (single backticks) is
        NOT excluded (adversarial M3).
        """
        import re as _re

        # Match both ``` and ~~~ fences (adversarial M2)
        fence_re = _re.compile(r"(```|~~~)")

        parts = fence_re.split(text)
        segments: list[tuple[str, bool]] = []
        in_code = False
        buf: list[str] = []
        for part in parts:
            if part in ("```", "~~~"):
                if not in_code:
                    if buf:
                        segments.append(("".join(buf), False))
                        buf = []
                    in_code = True
                    buf.append(part)
                else:
                    buf.append(part)
                    segments.append(("".join(buf), True))
                    buf = []
                    in_code = False
            else:
                buf.append(part)
        if buf:
            segments.append(("".join(buf), in_code))
        return segments

    def _re_split_title(s: str) -> str:
        """Strip trailing Markdown image title: url "Title" or url 'Title' (R3-2, M4)."""
        import re as _re

        return _re.split(r'\s+["\']', s)[0].strip()

    def _replace_std(match: re.Match) -> str:
        alt, src = match.group(1), match.group(2)
        if src.startswith(("/", "data:")) or "://" in src:
            return match.group(0)
        # Strip optional Markdown image title: ![alt](path "Title") or ![alt](path 'Title') (Copilot R3-2, M4)
        src = _re_split_title(src)
        src = unquote(src)  # decode %20 etc. before resolving (R2-2)
        abs_path = (base_dir / src).resolve()
        # Containment check: reject images that resolve outside vault_root (grok F1).
        if vault_root is not None and not abs_path.is_relative_to(Path(str(vault_root)).resolve()):
            return f'![{alt}](about:blank)'
        return f'![{alt}]({abs_path.as_uri()})'

    def _replace_wiki(match: re.Match) -> str:
        src = match.group(1)
        # Strip Obsidian size/alias suffix: ![[diagram.png|400]] → diagram.png (R2-3)
        src = src.split("|")[0]
        if src.startswith(("/", "data:")) or "://" in src:
            return match.group(0)
        src = unquote(src)  # decode %20 etc. before resolving (R2-2)
        # Resolve wiki-embeds against vault root, not note dir (Copilot R3-3)
        resolve_base = vault_root if vault_root is not None else base_dir
        abs_path = (resolve_base / src).resolve()
        return f'![{src}]({abs_path.as_uri()})'

    # Apply image resolution only outside fenced code blocks (Copilot R3-4)
    segments = _split_code_blocks(content)
    processed = []
    for seg, is_code in segments:
        if is_code:
            processed.append(seg)
        else:
            seg = _WIKI_EMBED_RE.sub(_replace_wiki, seg)
            seg = _IMG_RE.sub(_replace_std, seg)
            processed.append(seg)
    return "".join(processed)


def md_to_html(md_path: str | os.PathLike, vault_root: str | os.PathLike | None = None) -> str:
    """Convert a single markdown file to an HTML body string.

    Strips YAML frontmatter, renders mermaid blocks to inline PNGs, converts to
    HTML via python-markdown (tables + fenced_code). Resolves relative image
    paths against the source file's directory (Copilot #6). Wiki-embeds are
    resolved against ``vault_root`` when provided (Copilot R3-3).

    Phase 5c AC-4: Obsidian wikilinks (``[[note]]``) are converted to their
    display text before markdown conversion (controlled by
    ``render.resolve_wikilinks``, default True). Phase 5c AC-3: the resulting
    HTML is sanitised via bleach to strip raw ``<script>``/``on*`` payloads
    (controlled by ``render.sanitize_html``, default True).
    """
    import markdown as md_lib

    md_path = Path(md_path)
    content = md_path.read_text(encoding="utf-8")
    content = strip_frontmatter(content)
    # Strip pulled-annotation marker blocks before rendering so they don't
    # round-trip into the published PDF (Phase 5b feedback loop, ARB R4).
    content = strip_marker_blocks(content)
    # AC-4: convert wikilinks to display text before markdown rendering.
    # config.get(key, path=...) — the 2nd arg is a config *path*, NOT a
    # default, so treat None as the default (True) explicitly.
    if get("render.resolve_wikilinks") is not False:
        content = _resolve_wikilinks(content)
    content = render_mermaid_blocks(content, vault_root=str(vault_root) if vault_root is not None else None)
    # Resolve relative image paths to absolute file URIs so Playwright can
    # load them from about:blank (Copilot #6). Expand ~ in vault_root
    # before resolving (adversarial C1 — default vault.path is "~/Documents/Obsidian").
    vr = Path(os.path.expanduser(str(vault_root))).resolve() if vault_root is not None else None
    content = _resolve_image_paths(content, md_path.parent, vault_root=vr)
    html = md_lib.markdown(content, extensions=["tables", "fenced_code"])
    # AC-3: sanitise raw HTML (strip <script>, on* handlers, etc.) unless
    # explicitly disabled.
    if get("render.sanitize_html") is not False:
        html = _sanitize_html(html)
    return html


def wrap_html(html_body: str, *, title: str = "Obsidian page", css: str | None = None) -> str:
    """Wrap an HTML body in a full document with the e-ink CSS stylesheet.

    CSS defaults are read from the ``[pdf]`` config section (Copilot #7).
    """
    if css is None:
        _fs = get("pdf.font_size")
        _ff = get("pdf.font_family")
        _cfs = get("pdf.code_font_size")
        css = build_css(
            font_size=int(_fs) if _fs is not None else 14,
            font_family=str(_ff) if _ff is not None else "Georgia",
            code_font_size=int(_cfs) if _cfs is not None else 12,
        )
    return (
        "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{title}</title>\n<style>\n{css}\n</style>\n</head>\n"
        f"<body>\n{html_body}\n</body>\n</html>"
    )


def md_to_pdf(
    md_path: str | os.PathLike,
    pdf_path: str | os.PathLike,
    *,
    title: str | None = None,
    vault_root: str | os.PathLike | None = None,
) -> str:
    """Convert a single markdown file to PDF (publish_page path).

    Returns ``pdf_path``.
    """
    if title is None:
        title = Path(md_path).stem
    html = wrap_html(md_to_html(md_path, vault_root=vault_root), title=title)
    html_to_pdf(html, pdf_path, title=title)
    n = page_count(pdf_path)
    size = os.path.getsize(pdf_path)
    if n >= 0:
        print(f"  PDF: {size} bytes, {n} pages", file=sys.stderr)
    else:
        print(f"  PDF: {size} bytes", file=sys.stderr)
    return str(pdf_path)


def folder_to_pdf(folder_path: str | os.PathLike, pdf_path: str | os.PathLike, vault_root: str | os.PathLike | None = None) -> str:
    """Combine all ``.md`` files in ``folder_path`` into one PDF.

    Each file becomes one section, ordered by filename, with a page break
    between entries.
    """
    md_files = list_md_files(folder_path)
    if not md_files:
        raise ValueError(f"No .md files found in {folder_path}")
    print(f"  Found {len(md_files)} markdown files", file=sys.stderr)

    sections = []
    for i, md_path in enumerate(md_files):
        body = md_to_html(md_path, vault_root=vault_root or folder_path)
        if i < len(md_files) - 1:
            sections.append(f'<div class="page-break">\n{body}\n</div>')
        else:
            sections.append(body)
    combined = "\n".join(sections)
    folder_name = Path(folder_path).name or "folder"
    html = wrap_html(combined, title=folder_name)
    html_to_pdf(html, pdf_path, title=folder_name)
    n = page_count(pdf_path)
    size = os.path.getsize(pdf_path)
    if n >= 0:
        print(f"  Combined PDF: {size} bytes, {n} pages", file=sys.stderr)
    else:
        print(f"  Combined PDF: {size} bytes", file=sys.stderr)
    return str(pdf_path)


def publish_page(
    md_path: str | os.PathLike,
    rm_folder: str | None = None,
    *,
    dry_run: bool = False,
    vault_root: str | os.PathLike | None = None,
    content_only: bool = False,
) -> tuple[str, int]:
    """Publish a single markdown page to reMarkable.

    Renders markdown → PDF (Playwright), uploads via ``rmapi put``. Returns the
    destination path on reMarkable. ``dry_run`` renders the PDF but skips upload.
    ``content_only`` passes ``--content-only`` to rmapi to replace the PDF
    content while preserving annotations (ARB item 4).
    """
    if rm_folder is None:
        rm_folder = get("remarkable.folder")
    if vault_root is None:
        vault_root = get("vault.path")
    name = Path(md_path).stem
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        pdf_path = f.name
    try:
        print(f"Rendering {md_path} → PDF...", file=sys.stderr)
        md_to_pdf(md_path, pdf_path, title=name, vault_root=vault_root)
        from .pdf_renderer import page_count as _page_count
        try:
            _pages = _page_count(pdf_path)
        except Exception:  # noqa: BLE001 — best-effort page count
            _pages = 0
        if dry_run:
            print(f"[dry-run] skipping upload; PDF at {pdf_path}", file=sys.stderr)
            return f"[dry-run] {rm_folder}/{name}", _pages
        print(f"Uploading to {rm_folder}...", file=sys.stderr)
        dest = rmapi_client.put(pdf_path, rm_folder, dest_name=name, content_only=content_only)
        print(f"Published {name} to {dest} on your reMarkable", file=sys.stderr)
        return dest, _pages
    finally:
        # Only clean up the temp PDF on non-dry-run paths (Copilot #8).
        # Dry-run preserves the PDF for user inspection.
        if not dry_run and os.path.exists(pdf_path):
            os.unlink(pdf_path)


def publish_folder(
    folder_path: str | os.PathLike,
    rm_folder: str | None = None,
    *,
    dry_run: bool = False,
    vault_root: str | os.PathLike | None = None,
    content_only: bool = False,
) -> tuple[str, int]:
    """Publish all ``.md`` files in a folder as a combined PDF to reMarkable."""
    if rm_folder is None:
        rm_folder = get("remarkable.folder")
    if vault_root is None:
        vault_root = get("vault.path")
    folder_name = Path(folder_path).name or "folder"
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        pdf_path = f.name
    try:
        print(f"Rendering folder {folder_path} → combined PDF...", file=sys.stderr)
        folder_to_pdf(folder_path, pdf_path, vault_root=vault_root)
        from .pdf_renderer import page_count as _page_count
        try:
            _pages = _page_count(pdf_path)
        except Exception:  # noqa: BLE001 — best-effort page count
            _pages = 0
        if dry_run:
            print(f"[dry-run] skipping upload; PDF at {pdf_path}", file=sys.stderr)
            return f"[dry-run] {rm_folder}/{folder_name}", _pages
        print(f"Uploading to {rm_folder}...", file=sys.stderr)
        dest = rmapi_client.put(pdf_path, rm_folder, dest_name=folder_name, content_only=content_only)
        print(f"Published {folder_name} to {dest} on your reMarkable", file=sys.stderr)
        return dest, _pages
    finally:
        # Only clean up the temp PDF on non-dry-run paths (Copilot #8).
        if not dry_run and os.path.exists(pdf_path):
            os.unlink(pdf_path)