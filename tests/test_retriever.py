"""Tests for the retriever pipeline — mocked rmapi + vision, no network (DC-5/6/7)."""

from __future__ import annotations

import datetime
from pathlib import Path
from unittest.mock import patch

from obsidian_rm_bridge import retriever


def test_format_annotations_with_content():
    out = retriever.format_annotations([(1, "Note one"), (3, "Note two")], date_str="2026-11-12")
    assert "## Annotations from reMarkable — 2026-11-12" in out
    assert "**Page 1:**" in out
    assert "Note one" in out
    assert "**Page 3:**" in out
    assert "Note two" in out


def test_format_annotations_empty():
    out = retriever.format_annotations([], date_str="2026-11-12")
    assert "## Annotations from reMarkable — 2026-11-12" in out
    assert "No annotations found" in out


def test_format_annotations_default_date():
    out = retriever.format_annotations([(1, "test")])
    assert datetime.date.today().isoformat() in out


def test_append_annotations(tmp_path):
    md = tmp_path / "page.md"
    md.write_text("# Original Page\n\nContent here.\n")
    retriever.append_annotations(md, "## Annotations from reMarkable — 2026-11-12\n\n**Page 1:**\n> Note\n")
    text = md.read_text()
    assert "# Original Page" in text
    assert "## Annotations from reMarkable — 2026-11-12" in text
    assert "> Note" in text


def test_render_pdf_to_pngs(tmp_path):
    import fitz

    # Build a minimal 2-page PDF in memory.
    doc = fitz.open()
    for _ in range(2):
        doc.new_page()
    pdf = tmp_path / "doc.pdf"
    doc.save(str(pdf))
    doc.close()
    out_dir = tmp_path / "pngs"
    pngs = retriever.render_pdf_to_pngs(pdf, out_dir, dpi=150)
    assert len(pngs) == 2
    assert all(Path(p).is_file() for p in pngs)
    assert all(p.endswith(".png") for p in pngs)


def test_retrieve_full_pipeline_mocked(tmp_path, tmp_config):
    """DC-5: refresh before geta; DC-7: annotations appended to source .md."""
    md = tmp_path / "my-page.md"
    md.write_text("# My Page\n\nOriginal content.\n")

    with patch("obsidian_rm_bridge.retriever.rmapi_client.refresh") as m_refresh, \
         patch("obsidian_rm_bridge.retriever.rmapi_client.geta", return_value="/tmp/fake.pdf") as m_geta, \
         patch("obsidian_rm_bridge.retriever.render_pdf_to_pngs", return_value=["/tmp/p1.png", "/tmp/p2.png"]) as m_render, \
         patch("obsidian_rm_bridge.retriever.vision_client.transcribe_pages",
               return_value=[(1, "Handwritten note")]) as m_trans:

        retriever.retrieve("my-page", md, rm_folder="/Obsidian", api_key="k", model="z-ai/glm-4.5v")

        m_refresh.assert_called_once()  # DC-5: refresh ran
        # geta got the /Obsidian/my-page path
        assert "/Obsidian/my-page" in m_geta.call_args[0][0]
        m_render.assert_called_once()
        m_trans.assert_called_once()
        assert m_trans.call_args.kwargs["model"] == "z-ai/glm-4.5v"

    text = md.read_text()
    assert "## Annotations from reMarkable" in text
    assert "Handwritten note" in text
    assert "Original content." in text


def test_retrieve_no_annotations(tmp_path, tmp_config):
    md = tmp_path / "page.md"
    md.write_text("# Page\n\nBody.\n")
    with patch("obsidian_rm_bridge.retriever.rmapi_client.refresh"), \
         patch("obsidian_rm_bridge.retriever.rmapi_client.geta", return_value="/tmp/fake.pdf"), \
         patch("obsidian_rm_bridge.retriever.render_pdf_to_pngs", return_value=["/tmp/p1.png"]), \
         patch("obsidian_rm_bridge.retriever.vision_client.transcribe_pages", return_value=[]):
        section = retriever.retrieve("page", md, rm_folder="/Obsidian", api_key="k")
    assert "No annotations found" in section
    assert "## Annotations from reMarkable" in md.read_text()