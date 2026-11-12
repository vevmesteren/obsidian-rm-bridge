"""Shared helpers for obsidian-rm-bridge."""

from __future__ import annotations

import os
import re
from pathlib import Path

__all__ = ["ensure_dir", "expand_path", "list_md_files", "strip_frontmatter"]


def strip_frontmatter(content: str) -> str:
    """Remove a leading YAML frontmatter block (``---\\n...\\n---``) from markdown.

    Frontmatter without a closing fence, or content that does not start with
    ``---``, is returned unchanged.
    """
    return re.sub(r'^---\n.*?\n---\n', '', content, count=1, flags=re.DOTALL)


def expand_path(path: str | os.PathLike) -> Path:
    """Expand ``~`` and environment variables, returning a ``Path``."""
    return Path(os.path.expandvars(os.path.expanduser(str(path))))


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