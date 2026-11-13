"""Tests for utils.strip_frontmatter and path helpers."""

from __future__ import annotations

import pytest

from obsidian_rm_bridge.utils import (
    ensure_dir,
    expand_path,
    expand_user_path,
    list_md_files,
    strip_frontmatter,
    strip_marker_blocks,
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


# --- Phase 5b: strip_marker_blocks ---


def test_strip_marker_blocks_removes_marker_and_body_to_eof():
    """Marker block AND annotation body text after it are removed (grok C3, R4).

    Stripping to EOF prevents the publish→pull feedback loop: annotation
    text that survives into the published PDF would round-trip as content.
    """
    content = (
        "# Note\n\n"
        '<!-- ormb:annotations doc="my-page" rev="abc12345" -->\n'
        "## Page 1\n\n> scribble\n"
    )
    # Everything from the marker to EOF is removed.
    assert strip_marker_blocks(content) == "# Note"


def test_strip_marker_blocks_no_blocks():
    content = "# Just a note\n\nNo markers here.\n"
    assert strip_marker_blocks(content) == content


def test_strip_marker_blocks_strips_from_first_marker_to_eof():
    """Multiple markers: everything from the FIRST marker to EOF is removed."""
    content = (
        "Keep me\n\n"
        '<!-- ormb:annotations doc="a" rev="11111111" -->\n'
        "annot1\n"
        '<!-- ormb:annotations doc="b" rev="22222222" -->\n'
        "annot2\n"
    )
    assert strip_marker_blocks(content) == "Keep me"


def test_strip_marker_blocks_preserves_content_before_marker():
    """Content before the first marker is preserved."""
    content = (
        "# Title\n\nSome content.\n\n"
        '<!-- ormb:annotations doc="x" rev="deadbeef" -->\n'
        "> annotation text\n"
    )
    result = strip_marker_blocks(content)
    assert "# Title" in result
    assert "Some content." in result
    assert "ormb:annotations" not in result
    assert "annotation text" not in result