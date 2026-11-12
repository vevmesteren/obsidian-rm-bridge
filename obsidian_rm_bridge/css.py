"""E-ink readable CSS for PDF rendering.

The stylesheet favours serif body text at a comfortable size for reMarkable's
e-ink display, and wraps code blocks so long lines never overflow the page.
Font sizes/families are parameterised so the ``[pdf]`` config section can
override them without touching this module.
"""

from __future__ import annotations

__all__ = ["build_css"]


def build_css(
    font_size: int = 14,
    font_family: str = "Georgia",
    code_font_size: int = 12,
) -> str:
    """Build the e-ink CSS stylesheet.

    Defaults mirror the proven veviki-remarkable-bridge sizing:
    14pt body, 22pt h1, 18pt h2, 15pt h3, 12pt code — all pre-wrapped.
    """
    return f"""
body {{
    font-family: {font_family}, 'Times New Roman', serif;
    font-size: {font_size}pt;
    line-height: 1.8;
    color: #222;
    margin: 0;
}}
h1 {{
    font-size: {font_size + 8}pt;
    border-bottom: 2px solid #666;
    padding-bottom: 4pt;
    margin-top: 20pt;
}}
h2 {{
    font-size: {font_size + 4}pt;
    margin-top: 16pt;
}}
h3 {{
    font-size: {font_size + 1}pt;
    margin-top: 12pt;
}}
code {{
    font-family: 'Courier New', monospace;
    font-size: {code_font_size}pt;
    background: #f0f0f0;
    padding: 1pt 3pt;
    white-space: pre-wrap;
    word-wrap: break-word;
    overflow-wrap: break-word;
}}
pre {{
    background: #f5f5f5;
    padding: 8pt;
    font-size: {code_font_size}pt;
    line-height: 1.5;
    white-space: pre-wrap;
    word-wrap: break-word;
    overflow-wrap: break-word;
}}
pre code {{
    background: none;
    padding: 0;
    white-space: pre-wrap;
    word-wrap: break-word;
    overflow-wrap: break-word;
}}
table {{
    border-collapse: collapse;
    width: 100%;
    margin: 8pt 0;
}}
th, td {{
    border: 1px solid #aaa;
    padding: 4pt 8pt;
    text-align: left;
    font-size: {code_font_size}pt;
}}
th {{
    background: #e0e0e0;
    font-weight: bold;
}}
img {{
    max-width: 90%;
    margin: 12pt auto;
    display: block;
}}
blockquote {{
    border-left: 3px solid #aaa;
    margin-left: 0;
    padding-left: 12pt;
    color: #444;
}}
.page-break {{
    page-break-after: always;
}}
"""