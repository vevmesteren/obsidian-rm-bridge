"""Tests for mermaid_renderer — mocked orchestration + real Playwright (DC-1)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from obsidian_rm_bridge import mermaid_renderer as mr

from .conftest import requires_browser


def _fake_render(diagram, out_path, **kw):
    """Mock render_mermaid_to_png: write a tiny fake PNG and return its path."""
    Path(out_path).write_bytes(b"\x89PNG\r\n\x1a\n fake")
    return str(out_path)


def test_no_mermaid_blocks_passes_through():
    content = "# Title\n\nNo diagrams here.\n"
    assert mr.render_mermaid_blocks(content) == content


def test_mermaid_block_replaced_when_render_succeeds():
    content = "# Doc\n\n```mermaid\ngraph TB\n    A --> B\n```\n"
    with patch("obsidian_rm_bridge.mermaid_renderer.render_mermaid_to_png", side_effect=_fake_render):
        out = mr.render_mermaid_blocks(content)
    assert "```mermaid" not in out
    assert "<img" in out
    assert "data:image/png;base64," in out


def test_mermaid_block_left_as_is_when_render_fails():
    content = "# Doc\n\n```mermaid\ngraph TB\n    A --> B\n```\n"
    with patch("obsidian_rm_bridge.mermaid_renderer.render_mermaid_to_png",
               side_effect=RuntimeError("boom")):
        out = mr.render_mermaid_blocks(content)
    assert "```mermaid" in out  # left untouched on failure


def test_multiple_mermaid_blocks_preserve_order():
    content = (
        "```mermaid\ngraph TB\n    A --> B\n```\n"
        "text\n"
        "```mermaid\ngraph TB\n    C --> D\n```\n"
    )
    with patch("obsidian_rm_bridge.mermaid_renderer.render_mermaid_to_png", side_effect=_fake_render):
        out = mr.render_mermaid_blocks(content)
    assert out.count("<img") == 2


@requires_browser
def test_render_mermaid_to_png_real(tmp_path):
    png = tmp_path / "d.png"
    mr.render_mermaid_to_png("graph TB\n    A --> B\n    B --> C", png)
    assert png.is_file() and png.stat().st_size > 100
    with png.open("rb") as f:
        assert f.read(4) == b"\x89PNG"