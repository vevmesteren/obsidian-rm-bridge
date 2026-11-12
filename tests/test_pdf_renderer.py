"""Tests for pdf_renderer — real Playwright HTML→PDF (DC-1)."""

from __future__ import annotations

from .conftest import requires_browser


@requires_browser
def test_html_to_pdf_produces_valid_pdf(tmp_path):
    from obsidian_rm_bridge.pdf_renderer import html_to_pdf

    html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'></head>"
        "<body><h1>Hello</h1><p>Playwright PDF</p></body></html>"
    )
    pdf = tmp_path / "out.pdf"
    html_to_pdf(html, pdf)
    assert pdf.is_file() and pdf.stat().st_size > 0
    with pdf.open("rb") as f:
        assert f.read(5) == b"%PDF-"


@requires_browser
def test_html_to_pdf_embeds_base64_image(tmp_path):
    """A base64-inline image (as mermaid blocks produce) must survive into the PDF."""
    from obsidian_rm_bridge.pdf_renderer import html_to_pdf

    # 1x1 red PNG
    png_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
    html = (
        "<!DOCTYPE html><html><body>"
        f"<img src='data:image/png;base64,{png_b64}'/>"
        "</body></html>"
    )
    pdf = tmp_path / "img.pdf"
    html_to_pdf(html, pdf)
    import fitz

    doc = fitz.open(str(pdf))
    has_img = any(len(doc[p].get_images()) > 0 for p in range(doc.page_count))
    doc.close()
    assert has_img


def test_page_count_missing_returns_minus_one(tmp_path):
    from obsidian_rm_bridge.pdf_renderer import page_count

    bad = tmp_path / "nope.pdf"
    assert page_count(bad) == -1