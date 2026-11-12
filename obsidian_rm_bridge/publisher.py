"""Publish pipeline: markdown → mermaid PNG → HTML → PDF → reMarkable upload.

Refactored from the proven veviki-remarkable-bridge ``publish.py``:
- mermaid rendering via Playwright (was mmdc) — :mod:`mermaid_renderer` (DC-1)
- HTML→PDF via Playwright (was weasyprint) — :mod:`pdf_renderer` (DC-1)
- upload via :mod:`rmapi_client` (never ``--force``, DC-8)
No veviki or Hermes paths — all configuration comes from :mod:`config` (DC-3).
"""

from __future__ import annotations

import os
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


def md_to_html(md_path: str | os.PathLike) -> str:
    """Convert a single markdown file to an HTML body string.

    Strips YAML frontmatter, renders mermaid blocks to inline PNGs, converts to
    HTML via python-markdown (tables + fenced_code).
    """
    import markdown as md_lib

    content = Path(md_path).read_text(encoding="utf-8")
    content = strip_frontmatter(content)
    content = render_mermaid_blocks(content)
    return md_lib.markdown(content, extensions=["tables", "fenced_code"])


def wrap_html(html_body: str, *, title: str = "Obsidian page", css: str | None = None) -> str:
    """Wrap an HTML body in a full document with the e-ink CSS stylesheet."""
    if css is None:
        css = build_css()
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
        if os.path.exists(pdf_path):
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
        if os.path.exists(pdf_path):
            os.unlink(pdf_path)