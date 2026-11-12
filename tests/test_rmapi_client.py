"""Tests for rmapi_client — mocked subprocess, no real cloud calls (DC-2)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from obsidian_rm_bridge import rmapi_client


def _ok(stdout="", stderr=""):
    return MagicMock(returncode=0, stdout=stdout, stderr=stderr)


def test_refresh_calls_rmapi_refresh():
    with patch("obsidian_rm_bridge.rmapi_client.subprocess.run", return_value=_ok()) as m:
        rmapi_client.refresh()
        args = m.call_args[0][0]
        assert args[0] == "rmapi"
        assert "refresh" in args


def test_refresh_failure_raises():
    with patch("obsidian_rm_bridge.rmapi_client.subprocess.run",
               return_value=MagicMock(returncode=1, stdout="", stderr="network error")), \
         pytest.raises(rmapi_client.RmapiError):
        rmapi_client.refresh()


def test_geta_downloads_and_finds_pdf(tmp_path):
    expected = tmp_path / "test-page.pdf"
    expected.write_bytes(b"%PDF-1.4 dummy")
    with patch("obsidian_rm_bridge.rmapi_client.subprocess.run", return_value=_ok()) as m:
        out = rmapi_client.geta("/Obsidian/test-page", tmp_path)
        cmd = m.call_args[0][0]
        assert cmd[0] == "rmapi"
        assert cmd[1] == "geta"
        assert "--a" in cmd
        assert "/Obsidian/test-page" in cmd
        assert out == str(expected)


def test_geta_failure_raises(tmp_path):
    with patch("obsidian_rm_bridge.rmapi_client.subprocess.run",
               return_value=MagicMock(returncode=1, stdout="", stderr="document has no pages")), \
         pytest.raises(rmapi_client.RmapiError):
        rmapi_client.geta("/Obsidian/test", tmp_path)


def test_put_never_uses_force(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with patch("obsidian_rm_bridge.rmapi_client.subprocess.run", return_value=_ok()) as m:
        dest = rmapi_client.put(str(pdf), "/Obsidian")
        cmd = m.call_args[0][0]
        assert cmd[0] == "rmapi"
        assert cmd[1] == "put"
        assert "--force" not in cmd  # DC-8
        assert cmd[3] == "/Obsidian"
        assert dest == "/Obsidian/doc"


def test_put_dest_name_override(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with patch("obsidian_rm_bridge.rmapi_client.subprocess.run", return_value=_ok()):
        dest = rmapi_client.put(str(pdf), "/Obsidian", dest_name="custom")
        assert dest == "/Obsidian/custom"


def test_put_missing_pdf_raises(tmp_path):
    with pytest.raises(rmapi_client.RmapiError):
        rmapi_client.put(str(tmp_path / "nope.pdf"), "/Obsidian")


def test_ls_returns_stdout():
    with patch("obsidian_rm_bridge.rmapi_client.subprocess.run",
               return_value=_ok(stdout="file1\nfile2\n")):
        out = rmapi_client.ls("/Obsidian")
        assert "file1" in out
        assert "file2" in out


def test_rm_calls_rmapi_rm():
    with patch("obsidian_rm_bridge.rmapi_client.subprocess.run", return_value=_ok()) as m:
        rmapi_client.rm("/Obsidian/page")
        cmd = m.call_args[0][0]
        assert cmd[0] == "rmapi"
        assert cmd[1] == "rm"
        assert "/Obsidian/page" in cmd


def test_mkdir_calls_rmapi_mkdir():
    with patch("obsidian_rm_bridge.rmapi_client.subprocess.run", return_value=_ok()) as m:
        rmapi_client.mkdir("/Obsidian")
        cmd = m.call_args[0][0]
        assert cmd[0] == "rmapi"
        assert cmd[1] == "mkdir"


def test_missing_binary_raises():
    with patch("obsidian_rm_bridge.rmapi_client.subprocess.run",
               side_effect=FileNotFoundError("rmapi")), pytest.raises(rmapi_client.RmapiError):
        rmapi_client.ls("/")