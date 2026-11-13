"""Thin subprocess wrapper around the rmapi (ddvk fork) binary.

All reMarkable cloud operations go through here (DC-2). ``put`` never uses
``--force`` (DC-8) — that **destroys annotations**, not creates duplicates
(corrected per upstream rmapi docs, ARB item 4).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
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
    "resolve_rmapi",
    "rm",
]

RMAPI_BIN = os.environ.get("ORB_RMAPI_BIN", "rmapi")


class RmapiError(RuntimeError):
    """rmapi invocation failed."""


def resolve_rmapi() -> str | None:
    """Resolve rmapi binary path in priority order (ARB item 7):

    1. ``ORB_RMAPI_BIN`` env var (if the file exists)
    2. ``config.rmapi.path`` (if set and the file exists)
    3. ``shutil.which("rmapi")`` (on PATH)
    4. ``~/.local/bin/rmapi`` (fallback, if the file exists)

    Returns the resolved path or ``None`` if nothing is found.
    """
    # 1. ORB_RMAPI_BIN env
    env_bin = os.environ.get("ORB_RMAPI_BIN")
    if env_bin and Path(env_bin).is_file():
        return env_bin
    # 2. config.rmapi.path
    try:
        from .config import get as cfg_get
        cfg_path = cfg_get("rmapi.path")
    except Exception:  # noqa: BLE001 — config may not be available
        cfg_path = None
    if cfg_path:
        p = Path(os.path.expanduser(str(cfg_path)))
        if p.is_file():
            return str(p)
    # 3. shutil.which("rmapi")
    found = shutil.which("rmapi")
    if found:
        return found
    # 4. ~/.local/bin/rmapi
    fallback = Path.home() / ".local" / "bin" / "rmapi"
    if fallback.is_file():
        return str(fallback)
    return None


def find_rmapi() -> str | None:
    """Return the rmapi binary path, or ``None`` if not found."""
    return resolve_rmapi()


def _resolved_bin() -> str:
    """Return the resolved rmapi path, falling back to ``"rmapi"`` for _run."""
    return resolve_rmapi() or RMAPI_BIN


def _run(args: list[str], *, timeout: int = 120, cwd: str | os.PathLike | None = None,
         capture: bool = True) -> subprocess.CompletedProcess:
    """Run rmapi with ``args``; raise :class:`RmapiError` on non-zero exit."""
    bin_path = _resolved_bin()
    cmd = [bin_path, *args]
    try:
        result = subprocess.run(
            cmd, check=False, capture_output=capture, text=True, timeout=timeout, cwd=cwd
        )
    except FileNotFoundError as e:
        raise RmapiError(f"rmapi binary not found ({bin_path})") from e
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


def put(pdf_path: str, dest_folder: str, dest_name: str | None = None, *,
        content_only: bool = False) -> str:
    """Upload a PDF to reMarkable via ``rmapi put``.

    Never uses ``--force`` (DC-8) — that **destroys annotations**, not creates
    duplicates (corrected per upstream rmapi docs, ARB item 4).
    rmapi takes the *folder only* as the destination and uses the source
    filename; ``dest_name`` overrides the source filename when needed.
    Returns the destination path ``<dest_folder>/<dest_name>``.

    When ``content_only=True``, passes ``--content-only`` to rmapi so the PDF
    content is replaced while preserving handwritten annotations (ARB item 4).

    The destination folder is created if it doesn't exist (Copilot #9).
    The PDF is staged under ``dest_name`` so rmapi uploads it with the correct
    filename (Copilot #10) — rmapi uses the *source* filename, not dest_name.
    """
    src = Path(pdf_path)
    if not src.is_file():
        raise RmapiError(f"PDF not found: {pdf_path}")
    if dest_name is None:
        dest_name = src.stem

    # Ensure the destination folder exists on reMarkable (Copilot #9).
    # mkdir is idempotent — if the folder already exists rmapi returns an error
    # we can ignore.
    try:
        mkdir(dest_folder)
    except RmapiError:
        pass  # Folder likely already exists.

    # Stage the PDF under the dest_name so rmapi uses it as the uploaded
    # filename (Copilot #10). rmapi names the uploaded document after the
    # source file, so a random temp name would break pull's lookup.
    # Use a unique temp directory to avoid overwriting existing files
    # in the shared temp dir (Copilot R2-4).
    with tempfile.TemporaryDirectory(prefix="ormb-stage-") as stage_dir:
        staged = Path(stage_dir) / f"{dest_name}.pdf"
        shutil.copy2(str(src), str(staged))
        put_args = ["put", str(staged), dest_folder]
        if content_only:
            put_args.append("--content-only")
        _run(put_args, timeout=120)
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