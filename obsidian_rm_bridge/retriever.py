"""Retrieve pipeline: download annotated PDF → render PNG → vision transcribe → append.

Refactored from the proven veviki-remarkable-bridge ``retrieve.py``:
- rmapi ``refresh`` is mandatory before ``geta`` (DC-5)
- every PDF page goes to the vision model — no pre-filtering by drawing count (DC-6)
- annotations appended as ``## Annotations from reMarkable — YYYY-MM-DD`` (DC-7)
- vision model is configurable (DC-4)
No veviki or Hermes paths — config comes from :mod:`config` (DC-3).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from . import config as cfg_mod
from . import rmapi_client, vision_client
from .config import get

__all__ = [
    "append_annotations",
    "format_annotations",
    "render_pdf_to_pngs",
    "retrieve",
    "retrieve_info",
    "retrieve_to_json",
]


def _pull_cache_path() -> Path:
    """Path to the pull cache JSON inside the config dir (Phase 5c AC-1)."""
    return Path(cfg_mod.CONFIG_DIR) / "pull_cache.json"


class PullCache:
    """On-disk cache of vision transcription results keyed by PDF sha256.

    Phase 5c AC-1: re-pulling an unchanged document (same PDF content hash)
    returns the cached transcription without calling the vision pipeline,
    so it doesn't pay OpenRouter again. If the annotations change, the PDF
    hash changes and the cache misses.

    The cache lives at ``{CONFIG_DIR}/pull_cache.json``. A missing or corrupt
    cache file is treated as an empty cache (never crashes).
    """

    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path) if path is not None else _pull_cache_path()

    def _load(self) -> dict:
        """Return the cache dict, or ``{}`` if missing/corrupt."""
        if not self.path.is_file():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            # Corrupt JSON or unreadable — treat as empty (AC-1 TC-3).
            return {}

    def get(self, pdf_hash: str) -> dict | None:
        """Return the cached entry for ``pdf_hash``, or ``None`` on miss."""
        return self._load().get(pdf_hash)

    def put(self, pdf_hash: str, entry: dict) -> None:
        """Store ``entry`` under ``pdf_hash``. Failures are logged to stderr,
        never raised — a cache write failure shouldn't break the pull."""
        data = self._load()
        data[pdf_hash] = entry
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError as e:  # best-effort cache
            print(f"Warning: could not write pull cache: {e}", file=sys.stderr)


def render_pdf_to_pngs(pdf_path: str | os.PathLike, output_dir: str | os.PathLike, *, dpi: int = 300) -> list:
    """Render every PDF page to a PNG at ``dpi`` (default 300) via pymupdf.

    Returns a list of PNG file paths, one per page, in page order.
    """
    import pymupdf as fitz

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    with fitz.open(str(pdf_path)) as doc:
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        png_paths = []
        for page_num in range(doc.page_count):
            pix = doc[page_num].get_pixmap(matrix=mat)
            png_path = out / f"page_{page_num + 1}.png"
            pix.save(str(png_path))
            png_paths.append(str(png_path))
    print(f"  Rendered {len(png_paths)} pages to PNG at {dpi} DPI", file=sys.stderr)
    return png_paths


def format_annotations(annotations: list, *, date_str: str | None = None) -> str:
    """Format annotations as a markdown section (Phase 5c format).

    Produces a single date-titled section with one bullet per annotation::

        ## [YYYY-MM-DD] Annotations

        - handwritten annotation text
        - another annotation
    """
    if date_str is None:
        date_str = datetime.date.today().isoformat()
    header = f"## [{date_str}] Annotations\n"
    if not annotations:
        return header + "\nNo annotations found.\n"
    lines = [header]
    for _page_num, text in annotations:
        # Each annotation becomes one bullet line; multiline text stays as one
        # bullet (whitespace collapsed) so the section reads as a flat list.
        flat = " ".join(text.split())
        lines.append(f"- {flat}")
    return "\n".join(lines) + "\n"


def append_annotations(md_path: str | os.PathLike, annotations_section: str) -> None:
    """Append an annotations section to the source markdown file (DC-7)."""
    with Path(md_path).open("a", encoding="utf-8") as f:
        f.write("\n")
        f.write(annotations_section)


def retrieve(
    page_name: str,
    md_path: str | os.PathLike,
    *,
    rm_folder: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> str:
    """Full retrieve pipeline: refresh → geta → render → vision → append.

    ``page_name`` is the page on reMarkable (e.g. ``my-page``); the source .md
    is resolved relative to the vault path when ``md_path`` is not absolute.
    Returns the formatted annotations section that was appended.
    """
    if rm_folder is None:
        rm_folder = get("remarkable.folder")
    if model is None:
        model = get("vision.model")
    if api_key is None:
        api_key = get("vision.openrouter_api_key")

    # Resolve the source markdown path against the vault when it is relative.
    md = Path(md_path)
    if not md.is_absolute():
        vault = get("vault.path")
        md = Path(os.path.expanduser(vault)) / md
    md_path = str(md)

    # Reject missing source notes before downloading (Copilot R3-6).
    # Without this, append_annotations creates an empty file and reports success.
    if not Path(md_path).is_file():
        raise FileNotFoundError(
            f"Source note not found: {md_path}. "
            f"Use --md to specify the correct path."
        )

    rm_path = f"{rm_folder.rstrip('/')}/{page_name}"
    with tempfile.TemporaryDirectory() as tmpdir:
        print("Refreshing reMarkable cloud index...", file=sys.stderr)
        rmapi_client.refresh()

        print(f"Downloading annotated PDF from {rm_path}...", file=sys.stderr)
        pdf_path = rmapi_client.geta(rm_path, tmpdir)

        print("Rendering PDF pages to PNG...", file=sys.stderr)
        png_paths = render_pdf_to_pngs(pdf_path, tmpdir)

        print(f"Transcribing annotations via {model}...", file=sys.stderr)
        annotations = vision_client.transcribe_pages(png_paths, api_key, model=model)

        section = format_annotations(annotations)
        append_annotations(md_path, section)

    if annotations:
        print(f"Appended {len(annotations)} page(s) of annotations to {md_path}", file=sys.stderr)
    else:
        print(f"No annotations found on {page_name}", file=sys.stderr)
    return section


def retrieve_to_json(
    page_name: str,
    *,
    rm_folder: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> dict:
    """Retrieve pipeline that returns sections as JSON data (ARB item 3).

    Like :func:`retrieve` but writes nothing to disk. Returns a dict with:
    ``sections`` (list of ``{"page": N, "text": "..."}``),
    ``doc_id``, ``rev`` (8-char sha256 prefix), ``total_pages``,
    ``annotated_pages``.
    """
    if rm_folder is None:
        rm_folder = get("remarkable.folder")
    if model is None:
        model = get("vision.model")
    if api_key is None:
        api_key = get("vision.openrouter_api_key")

    rm_path = f"{rm_folder.rstrip('/')}/{page_name}"
    with tempfile.TemporaryDirectory() as tmpdir:
        print("Refreshing reMarkable cloud index...", file=sys.stderr)
        rmapi_client.refresh()

        print(f"Downloading annotated PDF from {rm_path}...", file=sys.stderr)
        pdf_path = rmapi_client.geta(rm_path, tmpdir)

        # AC-1: cache by PDF content hash so re-pulling an unchanged document
        # skips the (paid) vision pipeline. The hash is over the downloaded
        # PDF bytes — if the annotations change, the PDF hash changes too.
        pdf_hash = hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()
        cache = PullCache()
        cached = cache.get(pdf_hash)
        if cached is not None:
            print("Cache hit — skipping vision pipeline", file=sys.stderr)
            return cached

        print("Rendering PDF pages to PNG...", file=sys.stderr)
        png_paths = render_pdf_to_pngs(pdf_path, tmpdir)
        total_pages = len(png_paths)

        print(f"Transcribing annotations via {model}...", file=sys.stderr)
        annotations = vision_client.transcribe_pages(png_paths, api_key, model=model)

    sections = [
        {"page": page_num, "text": text}
        for page_num, text in annotations
    ]
    # Short revision hash so the plugin can stamp a marker block
    # (<!-- ormb:annotations doc="..." rev="..." -->) for replace-not-duplicate
    # semantics on re-pull (Phase 5b, ARB R4). Content-based, not time-based
    # (grok warning) — same annotations → same rev → idempotent re-pull.
    rev = hashlib.sha256(
        json.dumps(sections, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:8]
    result = {
        "sections": sections,
        "doc_id": page_name,
        "rev": rev,
        "total_pages": total_pages,
        "annotated_pages": len(sections),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    # AC-1: store the result so the next pull of the same PDF hits the cache.
    cache.put(pdf_hash, result)
    return result


def retrieve_info(
    page_name: str,
    *,
    rm_folder: str | None = None,
) -> dict:
    """Download + render a PDF and return page counts WITHOUT calling vision.

    Phase 5c AC-5: the plugin's consent modal needs to show the page count
    before consenting to vision cost. ``annotated_pages`` equals
    ``total_pages`` here (all pages are sent to vision; the real annotated
    count is only known after transcription).

    Returns ``{"total_pages": N, "annotated_pages": N}``.
    """
    if rm_folder is None:
        rm_folder = get("remarkable.folder")

    rm_path = f"{rm_folder.rstrip('/')}/{page_name}"
    with tempfile.TemporaryDirectory() as tmpdir:
        print("Refreshing reMarkable cloud index...", file=sys.stderr)
        rmapi_client.refresh()

        print(f"Downloading annotated PDF from {rm_path}...", file=sys.stderr)
        pdf_path = rmapi_client.geta(rm_path, tmpdir)

        print("Rendering PDF pages to PNG (info mode)...", file=sys.stderr)
        png_paths = render_pdf_to_pngs(pdf_path, tmpdir)
        total_pages = len(png_paths)

    print(f"Info: {total_pages} page(s) on {page_name}", file=sys.stderr)
    return {"total_pages": total_pages, "annotated_pages": total_pages}