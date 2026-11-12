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
from .utils import list_md_files, strip_frontmatter

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


def _resolve_image_paths(content: str, base_dir: Path) -> str:
    """Resolve relative image paths to absolute file:// URIs (Copilot #6).

    Handles both standard markdown ``![alt](src)`` and Obsidian wiki-embed
    ``![[image.png]]`` syntax (adversarial review: wiki-embeds are Obsidian's
    default image syntax). Absolute paths and URLs are left unchanged.

    Percent-encoded paths (``My%20diagram.png``) are decoded before resolving
    (Copilot R2-2). Obsidian wiki-embed size suffixes (``![[diagram.png|400]]``)
    are stripped before resolving (Copilot R2-3).
    """
    from urllib.parse import unquote

    def _replace_std(match: re.Match) -> str:
        alt, src = match.group(1), match.group(2)
        if src.startswith(("/", "data:")) or "://" in src:
            return match.group(0)
        src = unquote(src)  # decode %20 etc. before resolving (R2-2)
        abs_path = (base_dir / src).resolve()
        return f'![{alt}]({abs_path.as_uri()})'

    def _replace_wiki(match: re.Match) -> str:
        src = match.group(1)
        # Strip Obsidian size/alias suffix: ![[diagram.png|400]] → diagram.png (R2-3)
        src = src.split("|")[0]
        if src.startswith(("/", "data:")) or "://" in src:
            return match.group(0)
        src = unquote(src)  # decode %20 etc. before resolving (R2-2)
        abs_path = (base_dir / src).resolve()
        return f'![{src}]({abs_path.as_uri()})'

    content = _WIKI_EMBED_RE.sub(_replace_wiki, content)
    return _IMG_RE.sub(_replace_std, content)


def md_to_html(md_path: str | os.PathLike) -> str:
    """Convert a single markdown file to an HTML body string.

    Strips YAML frontmatter, renders mermaid blocks to inline PNGs, converts to
    HTML via python-markdown (tables + fenced_code). Resolves relative image
    paths against the source file's directory (Copilot #6).
    """
    import markdown as md_lib

    md_path = Path(md_path)
    content = md_path.read_text(encoding="utf-8")
    content = strip_frontmatter(content)
    content = render_mermaid_blocks(content)
    # Resolve relative image paths to absolute file URIs so Playwright can
    # load them from about:blank (Copilot #6).
    content = _resolve_image_paths(content, md_path.parent)
    return md_lib.markdown(content, extensions=["tables", "fenced_code"])


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
) -> str:
    """Convert a single markdown file to PDF (publish_page path).

    Returns ``pdf_path``.
    """
    if title is None:
        title = Path(md_path).stem
    html = wrap_html(md_to_html(md_path), title=title)
    html_to_pdf(html, pdf_path, title=title)
    n = page_count(pdf_path)
    size = os.path.getsize(pdf_path)
    if n >= 0:
        print(f"  PDF: {size} bytes, {n} pages", file=sys.stderr)
    else:
        print(f"  PDF: {size} bytes", file=sys.stderr)
    return str(pdf_path)


def folder_to_pdf(folder_path: str | os.PathLike, pdf_path: str | os.PathLike) -> str:
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
        body = md_to_html(md_path)
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
) -> str:
    """Publish a single markdown page to reMarkable.

    Renders markdown → PDF (Playwright), uploads via ``rmapi put``. Returns the
    destination path on reMarkable. ``dry_run`` renders the PDF but skips upload.
    """
    if rm_folder is None:
        rm_folder = get("remarkable.folder")
    name = Path(md_path).stem
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        pdf_path = f.name
    try:
        print(f"Rendering {md_path} → PDF...", file=sys.stderr)
        md_to_pdf(md_path, pdf_path, title=name)
        if dry_run:
            print(f"[dry-run] skipping upload; PDF at {pdf_path}", file=sys.stderr)
            return f"[dry-run] {rm_folder}/{name}"
        print(f"Uploading to {rm_folder}...", file=sys.stderr)
        dest = rmapi_client.put(pdf_path, rm_folder, dest_name=name)
        print(f"Published {name} to {dest} on your reMarkable", file=sys.stderr)
        return dest
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
) -> str:
    """Publish all ``.md`` files in a folder as a combined PDF to reMarkable."""
    if rm_folder is None:
        rm_folder = get("remarkable.folder")
    folder_name = Path(folder_path).name or "folder"
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        pdf_path = f.name
    try:
        print(f"Rendering folder {folder_path} → combined PDF...", file=sys.stderr)
        folder_to_pdf(folder_path, pdf_path)
        if dry_run:
            print(f"[dry-run] skipping upload; PDF at {pdf_path}", file=sys.stderr)
            return f"[dry-run] {rm_folder}/{folder_name}"
        print(f"Uploading to {rm_folder}...", file=sys.stderr)
        dest = rmapi_client.put(pdf_path, rm_folder, dest_name=folder_name)
        print(f"Published {folder_name} to {dest} on your reMarkable", file=sys.stderr)
        return dest
    finally:
        # Only clean up the temp PDF on non-dry-run paths (Copilot #8).
        if not dry_run and os.path.exists(pdf_path):
            os.unlink(pdf_path)