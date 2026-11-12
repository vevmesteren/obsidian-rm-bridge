"""Tests for utils.strip_frontmatter and path helpers."""

from __future__ import annotations

import pytest

from obsidian_rm_bridge.utils import ensure_dir, expand_path, list_md_files, strip_frontmatter


def test_strip_frontmatter():
    assert strip_frontmatter("---\ntitle: Test\n---\n# Hello\n") == "# Hello\n"


def test_strip_frontmatter_none():
    assert strip_frontmatter("# Hello\n") == "# Hello\n"


def test_strip_frontmatter_leaves_unterminated():
    # No closing fence -> left untouched.
    assert strip_frontmatter("---\ntitle: Test\n# Hello\n") == "---\ntitle: Test\n# Hello\n"


def test_expand_path(tmp_path, monkeypatch):
    monkeypatch.setenv("ORB_VAR", "subdir")
    p = expand_path("$ORB_VAR/file.txt")
    assert str(p).endswith("subdir/file.txt")


def test_ensure_dir(tmp_path):
    d = ensure_dir(tmp_path / "a" / "b")
    assert d.is_dir()


def test_list_md_files_sorted(tmp_path):
    for n in ("zebra.md", "alpha.md", "middle.md", "notes.txt"):
        (tmp_path / n).write_text("x")
    files = list_md_files(tmp_path)
    assert [f.name for f in files] == ["alpha.md", "middle.md", "zebra.md"]


def test_list_md_files_not_a_dir(tmp_path):
    f = tmp_path / "f.md"
    f.write_text("x")
    with pytest.raises(NotADirectoryError):
        list_md_files(f)