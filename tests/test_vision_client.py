"""Tests for vision_client — mocked OpenRouter API, no network (DC-4)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from obsidian_rm_bridge import vision_client


def _mock_response(text: str):
    r = MagicMock()
    r.json.return_value = {"choices": [{"message": {"content": text}}]}
    r.raise_for_status = MagicMock()
    return r


def test_transcribe_page_returns_text(tmp_path):
    png = tmp_path / "p.png"
    png.write_bytes(b"fake png")
    with patch("obsidian_rm_bridge.vision_client.requests.post", return_value=_mock_response("Buy milk and eggs")):
        assert vision_client.transcribe_page(png, "fake-key") == "Buy milk and eggs"


def test_transcribe_page_no_annotations_returns_none(tmp_path):
    png = tmp_path / "p.png"
    png.write_bytes(b"fake png")
    with patch("obsidian_rm_bridge.vision_client.requests.post", return_value=_mock_response("No annotations")):
        assert vision_client.transcribe_page(png, "fake-key") is None


def test_transcribe_page_real_text_containing_no_annotations_phrase(tmp_path):
    """Copilot #11: text containing 'no annotations' as part of a longer
    sentence is NOT filtered — only the exact sentinel match returns None."""
    png = tmp_path / "p.png"
    png.write_bytes(b"fake png")
    with patch("obsidian_rm_bridge.vision_client.requests.post",
               return_value=_mock_response("No annotations on the previous draft; review this change.")):
        result = vision_client.transcribe_page(png, "fake-key")
        assert result is not None
        assert "No annotations on the previous draft" in result


def test_transcribe_page_sends_default_model(tmp_path):
    png = tmp_path / "p.png"
    png.write_bytes(b"fake png")
    with patch("obsidian_rm_bridge.vision_client.requests.post", return_value=_mock_response("Note")) as m:
        vision_client.transcribe_page(png, "fake-key")
        body = m.call_args[1]["json"]
        assert body["model"] == "z-ai/glm-4.5v"  # DC-4 default
        content = body["messages"][0]["content"]
        assert content[1]["type"] == "image_url"
        assert "data:image/png;base64," in content[1]["image_url"]["url"]


def test_transcribe_page_configurable_model(tmp_path):
    png = tmp_path / "p.png"
    png.write_bytes(b"fake png")
    with patch("obsidian_rm_bridge.vision_client.requests.post", return_value=_mock_response("Note")) as m:
        vision_client.transcribe_page(png, "fake-key", model="gpt-4o")
        assert m.call_args[1]["json"]["model"] == "gpt-4o"


def test_transcribe_page_missing_key_raises(tmp_path):
    png = tmp_path / "p.png"
    png.write_bytes(b"fake png")
    with pytest.raises(RuntimeError):
        vision_client.transcribe_page(png, "")


def test_transcribe_pages_filters_empty(tmp_path):
    pngs = [str(tmp_path / f"p{i}.png") for i in range(3)]
    for p in pngs:
        Path(p).write_bytes(b"x")
    with patch("obsidian_rm_bridge.vision_client.transcribe_page",
               side_effect=["Note 1", None, "Note 3"]):
        out = vision_client.transcribe_pages(pngs, "fake-key")
    assert out == [(1, "Note 1"), (3, "Note 3")]


def test_transcribe_pages_continues_on_error(tmp_path):
    """Adversarial review: a transient API error on one page should not
    abort the entire pull — other pages should still be transcribed."""
    pngs = [str(tmp_path / f"p{i}.png") for i in range(3)]
    for p in pngs:
        Path(p).write_bytes(b"x")
    with patch("obsidian_rm_bridge.vision_client.transcribe_page",
               side_effect=["Note 1", RuntimeError("API timeout"), "Note 3"]):
        out = vision_client.transcribe_pages(pngs, "fake-key")
    assert out == [(1, "Note 1"), (3, "Note 3")]


def test_cross_verify_returns_both(tmp_path):
    png = tmp_path / "p.png"
    png.write_bytes(b"x")
    with patch("obsidian_rm_bridge.vision_client.transcribe_page",
               side_effect=["primary note", "verify note"]):
        prim, ver = vision_client.cross_verify(png, "k")
    assert prim == "primary note"
    assert ver == "verify note"