"""Shared helpers for obsidian-rm-bridge."""

from __future__ import annotations

import os
import re
from pathlib import Path

__all__ = ["ensure_dir", "expand_path", "expand_user_path", "list_md_files", "strip_frontmatter"]


def strip_frontmatter(content: str) -> str:
    """Remove a leading YAML frontmatter block (``---\\n...\\n---``) from markdown.

    Frontmatter without a closing fence, or content that does not start with
    ``---``, is returned unchanged. Handles both LF and CRLF line endings
    (adversarial review: CRLF support).
    """
    return re.sub(r'^---\r?\n.*?\r?\n---\r?\n', '', content, count=1, flags=re.DOTALL)


def expand_path(path: str | os.PathLike) -> Path:
    """Expand ``~`` and environment variables, returning a ``Path``.

    Used for **config values** — argv paths should use :func:`expand_user_path`
    instead so that ``$`` in filenames (e.g. ``Budget $HOME.md``) is not
    expanded (ARB item 6).
    """
    return Path(os.path.expandvars(os.path.expanduser(str(path))))


def expand_user_path(path: str | os.PathLike) -> Path:
    """Expand ``~`` only (NO ``expandvars``), returning a ``Path``.

    Used for CLI argv paths (``--md``, ``--vault``) so that filenames
    containing ``$`` are not mangled by variable expansion (ARB item 6).
    """
    return Path(os.path.expanduser(str(path)))


def ensure_dir(path: str | os.PathLike) -> Path:
    """Create ``path`` (and parents) if missing; return the ``Path``."""
    p = expand_path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def list_md_files(folder: str | os.PathLike) -> list[Path]:
    """Return all ``.md`` files in ``folder`` sorted by filename (case-sensitive)."""
    d = expand_path(folder)
    if not d.is_dir():
        raise NotADirectoryError(f"{d} is not a directory")
    return sorted([f for f in d.iterdir() if f.is_file() and f.suffix == ".md"], key=lambda p: p.name)