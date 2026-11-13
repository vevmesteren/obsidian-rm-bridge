"""Tests for the publisher pipeline — mocked rmapi + real Playwright rendering."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from obsidian_rm_bridge import publisher

from .conftest import requires_browser

# --- pure-logic (no browser) -----------------------------------------------


def test_md_to_html_basic(tmp_path):
    md = tmp_path / "page.md"
    md.write_text("# Title\n\nSome **bold** text.\n")
    html = publisher.md_to_html(md)
    assert "<h1>Title</h1>" in html
    assert "<strong>bold</strong>" in html


def test_md_to_html_strips_frontmatter(tmp_path):
    md = tmp_path / "page.md"
    md.write_text("---\ntitle: Test\ntags: [a, b]\n---\n# Page\n\nContent.\n")
    html = publisher.md_to_html(md)
    assert "title: Test" not in html
    assert "<h1>Page</h1>" in html


def test_md_to_html_table(tmp_path):
    md = tmp_path / "page.md"
    md.write_text("| Col A | Col B |\n|-------|-------|\n| 1 | 2 |\n")
    html = publisher.md_to_html(md)
    assert "<table>" in html
    assert "<th>Col A</th>" in html
    assert "<td>1</td>" in html


def test_wrap_html_valid_document():
    html = publisher.wrap_html("<h1>Test</h1>", title="My Page")
    assert "<!DOCTYPE html>" in html
    assert "<html>" in html
    assert "<title>My Page</title>" in html


def test_folder_to_pdf_empty_raises(tmp_path):
    with pytest.raises(ValueError):
        publisher.folder_to_pdf(tmp_path, str(tmp_path / "out.pdf"))


def test_publish_page_uploads_via_rmapi(tmp_path):
    md = tmp_path / "Test.md"
    md.write_text("# Test\n\nContent.\n")
    with patch("obsidian_rm_bridge.publisher.rmapi_client.put", return_value="/Obsidian/Test") as m, \
         patch("obsidian_rm_bridge.publisher.html_to_pdf") as mock_pdf:
        dest, _pages = publisher.publish_page(md, rm_folder="/Obsidian")
        assert dest == "/Obsidian/Test"
        m.assert_called_once()
        # dest_name defaults to the .md stem
        assert m.call_args.kwargs.get("dest_name") == "Test"
        mock_pdf.assert_called_once()


def test_publish_page_dry_run_skips_upload(tmp_path):
    md = tmp_path / "Test.md"
    md.write_text("# Test\n")
    with patch("obsidian_rm_bridge.publisher.rmapi_client.put") as m_put, \
         patch("obsidian_rm_bridge.publisher.html_to_pdf"):
        dest, _pages = publisher.publish_page(md, rm_folder="/Obsidian", dry_run=True)
    assert "dry-run" in dest
    m_put.assert_not_called()


def test_publish_folder_uploads_via_rmapi(tmp_path):
    for n in ("a.md", "b.md"):
        (tmp_path / n).write_text(f"# {n}\n")
    with patch("obsidian_rm_bridge.publisher.rmapi_client.put", return_value="/Obsidian/folder") as m, \
         patch("obsidian_rm_bridge.publisher.html_to_pdf"):
        dest, _pages = publisher.publish_folder(tmp_path, rm_folder="/Obsidian")
        assert dest == "/Obsidian/folder"
        m.assert_called_once()


def test_publish_page_failure_propagates(tmp_path):
    md = tmp_path / "Test.md"
    md.write_text("# Test\n")
    with patch("obsidian_rm_bridge.publisher.rmapi_client.put",
               side_effect=RuntimeError("upload failed")), \
         patch("obsidian_rm_bridge.publisher.html_to_pdf"), \
         pytest.raises(RuntimeError, match="upload failed"):
        publisher.publish_page(md, rm_folder="/Obsidian")


# --- image path resolution (Copilot R2/R3) ---------------------------------


def test_resolve_image_paths_strips_markdown_title(tmp_path):
    """Copilot R3-2: ![alt](path "Title") should resolve 'path', not 'path "Title"'."""
    img = tmp_path / "figure.png"
    img.write_bytes(b"x")
    md_content = '![Figure](figure.png "Caption")'
    result = publisher._resolve_image_paths(md_content, tmp_path)
    assert "figure.png" in result
    assert "%22" not in result  # no percent-encoded quotes from title


def test_resolve_image_paths_strips_single_quote_title(tmp_path):
    """Adversarial M4: ![alt](path 'Title') should also strip the title."""
    img = tmp_path / "figure.png"
    img.write_bytes(b"x")
    md_content = "![Figure](figure.png 'Caption')"
    result = publisher._resolve_image_paths(md_content, tmp_path)
    assert "figure.png" in result
    assert "%27" not in result  # no percent-encoded single quotes from title


def test_resolve_wiki_embeds_against_vault_root(tmp_path):
    """Copilot R3-3: ![[Attachments/chart.png]] from vault/Projects/ should
    resolve against vault root, not note directory."""
    vault = tmp_path
    (vault / "Attachments").mkdir()
    (vault / "Attachments" / "chart.png").write_bytes(b"x")
    (vault / "Projects").mkdir()
    md_content = "![[Attachments/chart.png]]"
    result = publisher._resolve_image_paths(
        md_content, vault / "Projects", vault_root=vault
    )
    assert "Attachments/chart.png" in result
    # Should NOT contain Projects/Attachments
    assert "Projects/Attachments" not in result


def test_resolve_image_paths_skips_code_blocks(tmp_path):
    """Copilot R3-4: image syntax inside fenced code blocks should not be rewritten."""
    img = tmp_path / "real.png"
    img.write_bytes(b"x")
    md_content = (
        "![Real](real.png)\n\n"
        "```markdown\n"
        "![Example](example.png)\n"
        "```\n"
    )
    result = publisher._resolve_image_paths(md_content, tmp_path)
    # The real image should be resolved to an absolute URI (exactly one file://)
    assert result.count("file://") == 1, "code-block image was rewritten"
    # The example inside code block should be unchanged
    assert "![Example](example.png)" in result


def test_resolve_image_paths_skips_tilde_fenced(tmp_path):
    """Adversarial M2: image syntax inside ~~~ fences should not be rewritten."""
    img = tmp_path / "real.png"
    img.write_bytes(b"x")
    md_content = (
        "![Real](real.png)\n\n"
        "~~~markdown\n"
        "![Tilde](tilde_img.png)\n"
        "~~~\n"
    )
    result = publisher._resolve_image_paths(md_content, tmp_path)
    assert result.count("file://") == 1, "tilde-fenced image was rewritten"
    assert "![Tilde](tilde_img.png)" in result


# --- real Playwright rendering (skipped if no browser) ---------------------


@requires_browser
def test_md_to_pdf_produces_valid_pdf(tmp_path):
    md = tmp_path / "page.md"
    md.write_text("# Test Page\n\nThis is a test.\n\n- Item 1\n- Item 2\n")
    pdf = tmp_path / "out.pdf"
    publisher.md_to_pdf(md, pdf)
    assert pdf.is_file() and pdf.stat().st_size > 0
    with pdf.open("rb") as f:
        assert f.read(5) == b"%PDF-"


@requires_browser
def test_md_to_pdf_renders_mermaid(tmp_path):
    """Acceptance: mermaid blocks render to an embedded image via Playwright (DC-1)."""
    md = tmp_path / "diagram.md"
    md.write_text("# Diagram\n\n```mermaid\ngraph TB\n    A --> B\n    B --> C\n```\n")
    pdf = tmp_path / "out.pdf"
    publisher.md_to_pdf(md, pdf)
    assert pdf.is_file() and pdf.stat().st_size > 0
    import fitz

    doc = fitz.open(str(pdf))
    n = doc.page_count
    # at least one page, and the page must contain at least one image (the mermaid PNG)
    has_image = any(len(doc[p].get_images()) > 0 for p in range(n))
    doc.close()
    assert n >= 1
    assert has_image, "mermaid diagram was not embedded as an image in the PDF"


@requires_browser
def test_folder_to_pdf_combines_files(tmp_path):
    for n in ("zebra.md", "alpha.md", "middle.md"):
        (tmp_path / n).write_text(f"# {n}\n\nContent of {n}.\n")
    pdf = tmp_path / "combined.pdf"
    publisher.folder_to_pdf(tmp_path, pdf)
    assert pdf.is_file() and pdf.stat().st_size > 0
    with pdf.open("rb") as f:
        assert f.read(5) == b"%PDF-"