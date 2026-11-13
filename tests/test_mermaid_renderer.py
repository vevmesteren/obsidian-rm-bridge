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


# --- Item 8: Mermaid security hardening ---


def test_mermaid_security_level_strict():
    """Item 8: HTML template must use securityLevel: 'strict'."""
    assert "securityLevel: 'strict'" in mr._HTML_TEMPLATE
    assert "securityLevel: 'loose'" not in mr._HTML_TEMPLATE


def test_mermaid_html_labels_false():
    """Item 8: HTML template must set htmlLabels: false."""
    assert "htmlLabels: false" in mr._HTML_TEMPLATE


def test_route_handler_allows_data_uri():
    """Item 8: route handler allows data: URIs."""
    from unittest.mock import MagicMock
    handler = mr._make_route_handler(vault_root=None)
    route = MagicMock()
    request = MagicMock(url="data:image/png;base64,abc")
    handler(route, request)
    route.continue_.assert_called_once()
    route.abort.assert_not_called()


def test_route_handler_allows_cdn():
    """Item 8: route handler allows the mermaid CDN URL."""
    from unittest.mock import MagicMock
    handler = mr._make_route_handler(vault_root=None)
    route = MagicMock()
    request = MagicMock(url=mr.MERMAID_JS_URL)
    handler(route, request)
    route.continue_.assert_called_once()
    route.abort.assert_not_called()


def test_route_handler_blocks_unknown(tmp_path):
    """Item 8: route handler aborts unknown URLs."""
    from unittest.mock import MagicMock
    handler = mr._make_route_handler(vault_root=tmp_path)
    route = MagicMock()
    request = MagicMock(url="https://evil.example.com/script.js")
    handler(route, request)
    route.abort.assert_called_once()
    route.continue_.assert_not_called()


def test_route_handler_blocks_out_of_vault_file(tmp_path):
    """Item 8: route handler aborts file:// URIs outside the vault."""
    from unittest.mock import MagicMock
    vault = tmp_path / "vault"
    vault.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    handler = mr._make_route_handler(vault_root=vault)
    route = MagicMock()
    request = MagicMock(url=f"file://{outside}")
    handler(route, request)
    route.abort.assert_called_once()


def test_route_handler_allows_in_vault_file(tmp_path):
    """Item 8: route handler allows file:// URIs inside the vault."""
    from unittest.mock import MagicMock
    vault = tmp_path / "vault"
    vault.mkdir()
    inside = vault / "image.png"
    inside.write_bytes(b"\x89PNG")
    handler = mr._make_route_handler(vault_root=vault)
    route = MagicMock()
    request = MagicMock(url=f"file://{inside}")
    handler(route, request)
    route.continue_.assert_called_once()