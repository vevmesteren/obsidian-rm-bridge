"""Tests for utils.strip_frontmatter and path helpers."""

from __future__ import annotations

import pytest

from obsidian_rm_bridge.utils import (
    ensure_dir,
    expand_path,
    expand_user_path,
    list_md_files,
    strip_frontmatter,
)


def test_strip_frontmatter():
    assert strip_frontmatter("---\ntitle: Test\n---\n# Hello\n") == "# Hello\n"


def test_strip_frontmatter_none():
    assert strip_frontmatter("# Hello\n") == "# Hello\n"


def test_strip_frontmatter_leaves_unterminated():
    # No closing fence -> left untouched.
    assert strip_frontmatter("---\ntitle: Test\n# Hello\n") == "---\ntitle: Test\n# Hello\n"


def test_strip_frontmatter_crlf():
    """Adversarial review: strip_frontmatter handles CRLF line endings."""
    content = "---\r\ntitle: Test\r\ntags: [a, b]\r\n---\r\n# Page\r\n\r\nContent.\r\n"
    result = strip_frontmatter(content)
    assert "title: Test" not in result
    assert "# Page" in result


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


# --- Item 6: expand_user_path does NOT expand vars ---


def test_expand_user_path_no_expandvars(tmp_path, monkeypatch):
    """Item 6: expand_user_path must not apply os.path.expandvars."""
    monkeypatch.setenv("ORB_VAR", "subdir")
    p = expand_user_path("$ORB_VAR/file.txt")
    assert "$ORB_VAR" in str(p)  # $ORB_VAR NOT expanded


def test_expand_user_path_expands_tilde(tmp_path, monkeypatch):
    """Item 6: expand_user_path still expands ~."""
    monkeypatch.setenv("HOME", str(tmp_path))
    p = expand_user_path("~/file.txt")
    assert str(p) == str(tmp_path / "file.txt")


def test_expand_path_still_expands_vars(tmp_path, monkeypatch):
    """Item 6: expand_path (for config values) still does expandvars."""
    monkeypatch.setenv("ORB_VAR", "subdir")
    p = expand_path("$ORB_VAR/file.txt")
    assert "subdir" in str(p)
    assert "$ORB_VAR" not in str(p)