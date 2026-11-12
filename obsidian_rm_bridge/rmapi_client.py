"""Thin subprocess wrapper around the rmapi (ddvk fork) binary.

All reMarkable cloud operations go through here (DC-2). ``put`` never uses
``--force`` (DC-8) — it would create duplicates rather than replacements.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

__all__ = [
    "RMAPI_BIN",
    "RmapiError",
    "find_rmapi",
    "geta",
    "ls",
    "mkdir",
    "pair",
    "put",
    "refresh",
    "rm",
]

RMAPI_BIN = os.environ.get("ORB_RMAPI_BIN", "rmapi")


class RmapiError(RuntimeError):
    """rmapi invocation failed."""


def find_rmapi() -> str | None:
    """Return the rmapi binary path, or ``None`` if not on PATH."""
    return shutil.which(RMAPI_BIN) if isinstance(RMAPI_BIN, str) else None


def _run(args: list[str], *, timeout: int = 120, cwd: str | os.PathLike | None = None,
         capture: bool = True) -> subprocess.CompletedProcess:
    """Run rmapi with ``args``; raise :class:`RmapiError` on non-zero exit."""
    cmd = [RMAPI_BIN, *args]
    try:
        result = subprocess.run(
            cmd, check=False, capture_output=capture, text=True, timeout=timeout, cwd=cwd
        )
    except FileNotFoundError as e:
        raise RmapiError(f"rmapi binary not found ({RMAPI_BIN})") from e
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "")[:300]
        raise RmapiError(f"rmapi {' '.join(args)} failed: {err}")
    return result


def refresh() -> subprocess.CompletedProcess:
    """Refresh the reMarkable cloud index.

    Mandatory before :func:`geta` — the cloud index is stale immediately after
    annotation, so without ``refresh`` ``geta`` fails with "the document has no
    pages." (DC-5).
    """
    return _run(["refresh"], timeout=60)


def geta(page_path: str, output_dir: str | os.PathLike) -> str:
    """Download the annotated (flattened image) PDF for ``page_path``.

    ``page_path`` is the full reMarkable path, e.g. ``/Obsidian/my-page``.
    rmapi writes ``<page-name>.pdf`` into ``output_dir``. Returns that path.
    """
    page_name = os.path.basename(page_path.rstrip("/"))
    _run(["geta", "--a", page_path], timeout=180, cwd=str(output_dir))
    expected = Path(output_dir) / f"{page_name}.pdf"
    if expected.is_file():
        return str(expected)
    # Fallback: any PDF rmapi happened to create.
    pdfs = sorted(p for p in Path(output_dir).glob("*.pdf"))
    if pdfs:
        return str(pdfs[0])
    raise RmapiError(f"rmapi geta produced no PDF in {output_dir}")


def put(pdf_path: str, dest_folder: str, dest_name: str | None = None) -> str:
    """Upload a PDF to reMarkable via ``rmapi put``.

    Never uses ``--force`` (DC-8) — that creates duplicates, not replacements.
    rmapi takes the *folder only* as the destination and uses the source
    filename; ``dest_name`` overrides the source filename when needed.
    Returns the destination path ``<dest_folder>/<dest_name>``.
    """
    src = Path(pdf_path)
    if not src.is_file():
        raise RmapiError(f"PDF not found: {pdf_path}")
    if dest_name is None:
        dest_name = src.stem
    # rmapi put <file> <folder> — uses the source filename automatically.
    _run(["put", str(src), dest_folder], timeout=120)
    return f"{dest_folder.rstrip('/')}/{dest_name}"


def ls(folder: str = "/") -> str:
    """List entries in a reMarkable folder; returns rmapi's stdout."""
    return _run(["ls", folder], timeout=60).stdout


def rm(page_path: str) -> subprocess.CompletedProcess:
    """Delete a file on reMarkable."""
    return _run(["rm", page_path], timeout=60)


def mkdir(folder: str) -> subprocess.CompletedProcess:
    """Create a folder on reMarkable."""
    return _run(["mkdir", folder], timeout=60)


def pair() -> int:
    """Interactively pair rmapi with reMarkable (prompts for the one-time code).

    The pairing URL is ``https://my.remarkable.com/device/desktop/connect``
    (NOT ``/device/connect/desktop`` — path segments swapped, returns 404).
    rmapi reads the code from stdin; this runs attached to the TTY.
    """
    url = "https://my.remarkable.com/device/desktop/connect"
    print(
        f"Open {url} in your browser, sign in, and copy the 8-character one-time "
        f"code. rmapi will prompt for it below.",
        file=sys.stderr,
    )
    return subprocess.run([RMAPI_BIN], check=False).returncode