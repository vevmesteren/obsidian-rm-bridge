"""Tests for the e-ink CSS stylesheet (MF-4/MF-5 sizing + code wrapping)."""

from __future__ import annotations

from obsidian_rm_bridge.css import build_css


def test_default_font_sizes():
    css = build_css()
    assert "14pt" in css  # body
    assert "22pt" in css  # h1 = 14+8
    assert "18pt" in css  # h2 = 14+4
    assert "15pt" in css  # h3 = 14+1
    assert "12pt" in css  # code


def test_code_wrapping():
    css = build_css()
    assert "white-space: pre-wrap" in css
    assert "word-wrap: break-word" in css
    assert "overflow-wrap: break-word" in css


def test_parameterised_fonts():
    css = build_css(font_size=18, font_family="Helvetica", code_font_size=14)
    assert "18pt" in css
    assert "Helvetica" in css
    assert "14pt" in css  # code