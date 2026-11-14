"""Tests for the retriever pipeline — mocked rmapi + vision, no network (DC-5/6/7)."""

from __future__ import annotations

import datetime
from pathlib import Path
from unittest.mock import patch

from obsidian_rm_bridge import retriever


def test_format_annotations_with_content():
    out = retriever.format_annotations([(1, "Note one"), (3, "Note two")], date_str="2026-11-12")
    assert "## [2026-11-12] Annotations" in out
    assert "- Note one" in out
    assert "- Note two" in out
    # New format: no page numbers, no blockquotes.
    assert "**Page" not in out
    assert ">" not in out


def test_format_annotations_empty():
    out = retriever.format_annotations([], date_str="2026-11-12")
    assert "## [2026-11-12] Annotations" in out
    assert "No annotations found" in out


def test_format_annotations_default_date():
    out = retriever.format_annotations([(1, "test")])
    assert datetime.date.today().isoformat() in out


def test_append_annotations(tmp_path):
    md = tmp_path / "page.md"
    md.write_text("# Original Page\n\nContent here.\n")
    retriever.append_annotations(md, "## [2026-11-12] Annotations\n\n- Note\n")
    text = md.read_text()
    assert "# Original Page" in text
    assert "## [2026-11-12] Annotations" in text
    assert "- Note" in text


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
    assert "## [" in text
    assert "Annotations" in text
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
    assert "## [" in md.read_text()


def test_format_annotations_multiline_collapses_to_one_bullet():
    """Phase 5c: a multiline transcription becomes a single bullet line
    (whitespace collapsed), not a multi-line blockquote."""
    text = "Line one\n\nLine two\n- bullet"
    out = retriever.format_annotations([(1, text)], date_str="2026-11-12")
    assert "## [2026-11-12] Annotations" in out
    assert "- Line one Line two - bullet" in out
    # Exactly one bullet line for one annotation.
    assert out.count("\n- ") == 1


def test_retrieve_missing_source_raises(tmp_path, tmp_config):
    """Copilot R3-6: missing source note should raise FileNotFoundError,
    not silently create an empty annotations-only file."""
    missing = tmp_path / "nonexistent.md"
    assert not missing.exists()
    import pytest
    with patch("obsidian_rm_bridge.retriever.rmapi_client.refresh"), \
         patch("obsidian_rm_bridge.retriever.rmapi_client.geta", return_value="/tmp/fake.pdf"), \
         patch("obsidian_rm_bridge.retriever.render_pdf_to_pngs", return_value=["/tmp/p1.png"]), \
         patch("obsidian_rm_bridge.retriever.vision_client.transcribe_pages",
               return_value=[(1, "Note")]), \
         pytest.raises(FileNotFoundError, match="Source note not found"):
        retriever.retrieve("page", missing, rm_folder="/Obsidian", api_key="k")
    # File should NOT have been created
    assert not missing.exists()


# --- Item 3: retrieve_to_json ---


def _make_pdf(tmp_path, name="doc.pdf", content=b"%PDF-1.4 fake pdf\n"):
    """Write a real on-disk PDF for tests that mock geta (AC-1 hashes the file)."""
    p = tmp_path / name
    p.write_bytes(content)
    return str(p)


def test_retrieve_to_json_returns_sections(tmp_path, tmp_config):
    """Item 3: retrieve_to_json returns sections, doc_id, total_pages, annotated_pages."""
    pdf = _make_pdf(tmp_path)
    with patch("obsidian_rm_bridge.retriever.rmapi_client.refresh"), \
         patch("obsidian_rm_bridge.retriever.rmapi_client.geta", return_value=pdf), \
         patch("obsidian_rm_bridge.retriever.render_pdf_to_pngs",
               return_value=["/tmp/p1.png", "/tmp/p2.png", "/tmp/p3.png"]), \
         patch("obsidian_rm_bridge.retriever.vision_client.transcribe_pages",
               return_value=[(1, "Note on page 1"), (3, "Note on page 3")]):
        result = retriever.retrieve_to_json("my-page", rm_folder="/Obsidian", api_key="k")
    assert result["doc_id"] == "my-page"
    assert result["total_pages"] == 3
    assert result["annotated_pages"] == 2
    assert len(result["sections"]) == 2
    assert result["sections"][0]["page"] == 1
    assert "Note on page 1" in result["sections"][0]["text"]
    assert result["sections"][1]["page"] == 3


def test_retrieve_to_json_no_file_write(tmp_path, tmp_config):
    """Item 3: retrieve_to_json must NOT write to disk."""
    md = tmp_path / "page.md"
    md.write_text("# Original\n")
    original = md.read_text()
    pdf = _make_pdf(tmp_path)
    with patch("obsidian_rm_bridge.retriever.rmapi_client.refresh"), \
         patch("obsidian_rm_bridge.retriever.rmapi_client.geta", return_value=pdf), \
         patch("obsidian_rm_bridge.retriever.render_pdf_to_pngs", return_value=["/tmp/p1.png"]), \
         patch("obsidian_rm_bridge.retriever.vision_client.transcribe_pages",
               return_value=[(1, "Note")]):
        retriever.retrieve_to_json("page", rm_folder="/Obsidian", api_key="k")
    # The source .md must be untouched
    assert md.read_text() == original


# --- Phase 5b: retrieve_to_json rev field + section shape ---


def test_retrieve_to_json_has_rev_field(tmp_path, tmp_config):
    """Phase 5b: retrieve_to_json returns a `rev` field (8-char sha256 hash)."""
    pdf = _make_pdf(tmp_path)
    with patch("obsidian_rm_bridge.retriever.rmapi_client.refresh"), \
         patch("obsidian_rm_bridge.retriever.rmapi_client.geta", return_value=pdf), \
         patch("obsidian_rm_bridge.retriever.render_pdf_to_pngs", return_value=["/tmp/p1.png"]), \
         patch("obsidian_rm_bridge.retriever.vision_client.transcribe_pages",
               return_value=[(1, "Note on page 1")]):
        result = retriever.retrieve_to_json("my-page", rm_folder="/Obsidian", api_key="k")
    assert "rev" in result
    rev = result["rev"]
    assert isinstance(rev, str)
    assert len(rev) == 8
    assert all(c in "0123456789abcdef" for c in rev)


def test_retrieve_to_json_section_text_is_raw(tmp_path, tmp_config):
    """Phase 5b: each section's `text` is the raw transcribed text, not a
    header-wrapped format_annotations block."""
    pdf = _make_pdf(tmp_path)
    with patch("obsidian_rm_bridge.retriever.rmapi_client.refresh"), \
         patch("obsidian_rm_bridge.retriever.rmapi_client.geta", return_value=pdf), \
         patch("obsidian_rm_bridge.retriever.render_pdf_to_pngs", return_value=["/tmp/p1.png"]), \
         patch("obsidian_rm_bridge.retriever.vision_client.transcribe_pages",
               return_value=[(1, "raw scribble"), (3, "more scribble")]):
        result = retriever.retrieve_to_json("my-page", rm_folder="/Obsidian", api_key="k")
    assert result["sections"][0]["text"] == "raw scribble"
    assert result["sections"][1]["text"] == "more scribble"
    # No repeated header inside each section.
    assert "Annotations" not in result["sections"][0]["text"]


# --- Phase 5c AC-1: pull cache by PDF hash ---


def test_retrieve_to_json_cache_hit_skips_vision(tmp_path, tmp_config):
    """AC-1 TC-1: first call misses → vision runs → cached; second call with
    the same PDF hits → vision NOT called, cached result returned."""
    pdf = _make_pdf(tmp_path, content=b"same-pdf-bytes")
    trans = patch("obsidian_rm_bridge.retriever.vision_client.transcribe_pages",
                  return_value=[(1, "Handwritten note")])
    with patch("obsidian_rm_bridge.retriever.rmapi_client.refresh"), \
         patch("obsidian_rm_bridge.retriever.rmapi_client.geta", return_value=pdf), \
         patch("obsidian_rm_bridge.retriever.render_pdf_to_pngs",
               return_value=["/tmp/p1.png", "/tmp/p2.png"]), \
         trans as m_trans:
        r1 = retriever.retrieve_to_json("my-page", rm_folder="/Obsidian", api_key="k")
        assert m_trans.call_count == 1
        r2 = retriever.retrieve_to_json("my-page", rm_folder="/Obsidian", api_key="k")
        assert m_trans.call_count == 1  # vision NOT called again
    assert r2 == r1  # cached result returned verbatim
    # Cache file exists in the config dir (not /tmp).
    cache_path = tmp_path / "orb-config" / "pull_cache.json"
    assert cache_path.is_file()
    import json
    data = json.loads(cache_path.read_text())
    assert len(data) == 1


def test_retrieve_to_json_cache_miss_on_changed_pdf(tmp_path, tmp_config):
    """AC-1 TC-2: different PDF content → different hash → miss → vision runs."""
    pdf_a = _make_pdf(tmp_path, "a.pdf", content=b"pdf-A-content")
    pdf_b = _make_pdf(tmp_path, "b.pdf", content=b"pdf-B-content")
    trans = patch("obsidian_rm_bridge.retriever.vision_client.transcribe_pages",
                  return_value=[(1, "Note")])
    geta_returns = [pdf_a, pdf_b]
    with patch("obsidian_rm_bridge.retriever.rmapi_client.refresh"), \
         patch("obsidian_rm_bridge.retriever.rmapi_client.geta", side_effect=geta_returns), \
         patch("obsidian_rm_bridge.retriever.render_pdf_to_pngs",
               return_value=["/tmp/p1.png"]), \
         trans as m_trans:
        retriever.retrieve_to_json("my-page", rm_folder="/Obsidian", api_key="k")
        retriever.retrieve_to_json("my-page", rm_folder="/Obsidian", api_key="k")
    assert m_trans.call_count == 2  # both calls ran vision (different PDFs)


def test_retrieve_to_json_corrupt_cache_does_not_crash(tmp_path, tmp_config):
    """AC-1 TC-3: a corrupt cache file is treated as empty; vision re-runs."""
    pdf = _make_pdf(tmp_path, content=b"some-pdf")
    cache_path = tmp_path / "orb-config" / "pull_cache.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text("{ this is not valid json !!! ")
    with patch("obsidian_rm_bridge.retriever.rmapi_client.refresh"), \
         patch("obsidian_rm_bridge.retriever.rmapi_client.geta", return_value=pdf), \
         patch("obsidian_rm_bridge.retriever.render_pdf_to_pngs",
               return_value=["/tmp/p1.png"]), \
         patch("obsidian_rm_bridge.retriever.vision_client.transcribe_pages",
               return_value=[(1, "Note")]) as m_trans:
        result = retriever.retrieve_to_json("my-page", rm_folder="/Obsidian", api_key="k")
    assert m_trans.call_count == 1  # vision ran despite corrupt cache
    assert result["sections"][0]["text"] == "Note"
    # The successful run rewrites the cache with valid JSON.
    import json
    json.loads(cache_path.read_text())


# --- Phase 5c AC-5: retrieve_info (page count without vision) ---


def test_retrieve_info_returns_page_count_without_vision(tmp_path, tmp_config):
    """AC-5 TC-1: retrieve_info returns total_pages from pymupdf page_count
    and does NOT call the vision model or render PNGs."""
    pdf = _make_pdf(tmp_path)
    with patch("obsidian_rm_bridge.retriever.rmapi_client.refresh"), \
         patch("obsidian_rm_bridge.retriever.rmapi_client.geta", return_value=pdf), \
         patch("obsidian_rm_bridge.retriever.render_pdf_to_pngs") as m_render, \
         patch("obsidian_rm_bridge.retriever.page_count", return_value=3) as m_count, \
         patch("obsidian_rm_bridge.retriever.vision_client.transcribe_pages") as m_trans:
        info = retriever.retrieve_info("my-page", rm_folder="/Obsidian")
    assert info["total_pages"] == 3
    assert info["annotated_pages"] == 3
    m_trans.assert_not_called()
    m_render.assert_not_called()