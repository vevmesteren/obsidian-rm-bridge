"""Tests for rmapi_client — mocked subprocess, no real cloud calls (DC-2)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from obsidian_rm_bridge import rmapi_client


def _ok(stdout="", stderr=""):
    return MagicMock(returncode=0, stdout=stdout, stderr=stderr)


def test_refresh_calls_rmapi_refresh():
    with patch("obsidian_rm_bridge.rmapi_client.resolve_rmapi", return_value="rmapi"), \
         patch("obsidian_rm_bridge.rmapi_client.subprocess.run", return_value=_ok()) as m:
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
    with patch("obsidian_rm_bridge.rmapi_client.resolve_rmapi", return_value="rmapi"), \
         patch("obsidian_rm_bridge.rmapi_client.subprocess.run", return_value=_ok()) as m:
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
    with patch("obsidian_rm_bridge.rmapi_client.resolve_rmapi", return_value="rmapi"), \
         patch("obsidian_rm_bridge.rmapi_client.subprocess.run", return_value=_ok()) as m:
        dest = rmapi_client.put(str(pdf), "/Obsidian")
        cmd = m.call_args[0][0]
        assert cmd[0] == "rmapi"
        assert cmd[1] == "put"
        assert "--force" not in cmd  # DC-8
        assert "/Obsidian" in cmd
        assert dest == "/Obsidian/doc"


def test_put_creates_dest_folder(tmp_path):
    """Copilot #9: put() should mkdir the destination folder before uploading."""
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with patch("obsidian_rm_bridge.rmapi_client.subprocess.run", return_value=_ok()) as m:
        rmapi_client.put(str(pdf), "/NewFolder")
        cmds = [call.args[0] for call in m.call_args_list]
        # First call should be mkdir, second should be put
        assert cmds[0][1] == "mkdir"
        assert "/NewFolder" in cmds[0]
        assert any(c[1] == "put" for c in cmds)


def test_put_stages_pdf_under_dest_name(tmp_path):
    """Copilot #10: put() should stage the PDF under dest_name so rmapi uploads
    it with the correct filename (rmapi uses the source filename)."""
    pdf = tmp_path / "tmp_random_name.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with patch("obsidian_rm_bridge.rmapi_client.subprocess.run", return_value=_ok()) as m:
        rmapi_client.put(str(pdf), "/Obsidian", dest_name="my-page")
        # Find the put command (not mkdir)
        put_calls = [call for call in m.call_args_list if call.args[0][1] == "put"]
        assert put_calls
        uploaded_file = put_calls[0].args[0][2]
        assert "my-page.pdf" in uploaded_file
        # Adversarial I5: verify staging uses a unique temp directory
        from pathlib import Path
        assert Path(uploaded_file).parent.name.startswith("ormb-stage-")


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
    with patch("obsidian_rm_bridge.rmapi_client.resolve_rmapi", return_value="rmapi"), \
         patch("obsidian_rm_bridge.rmapi_client.subprocess.run", return_value=_ok()) as m:
        rmapi_client.rm("/Obsidian/page")
        cmd = m.call_args[0][0]
        assert cmd[0] == "rmapi"
        assert cmd[1] == "rm"
        assert "/Obsidian/page" in cmd


def test_mkdir_calls_rmapi_mkdir():
    with patch("obsidian_rm_bridge.rmapi_client.resolve_rmapi", return_value="rmapi"), \
         patch("obsidian_rm_bridge.rmapi_client.subprocess.run", return_value=_ok()) as m:
        rmapi_client.mkdir("/Obsidian")
        cmd = m.call_args[0][0]
        assert cmd[0] == "rmapi"
        assert cmd[1] == "mkdir"


def test_missing_binary_raises():
    with patch("obsidian_rm_bridge.rmapi_client.subprocess.run",
               side_effect=FileNotFoundError("rmapi")), pytest.raises(rmapi_client.RmapiError):
        rmapi_client.ls("/")


# --- Item 4: content-only put ---


def test_put_content_only_flag(tmp_path):
    """Item 4: put(content_only=True) passes --content-only to rmapi."""
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with patch("obsidian_rm_bridge.rmapi_client.subprocess.run", return_value=_ok()) as m:
        rmapi_client.put(str(pdf), "/Obsidian", dest_name="doc", content_only=True)
        put_calls = [call for call in m.call_args_list if call.args[0][1] == "put"]
        assert put_calls
        cmd = put_calls[0].args[0]
        assert "--content-only" in cmd


def test_put_no_content_only_by_default(tmp_path):
    """Item 4: put() without content_only does NOT pass --content-only."""
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with patch("obsidian_rm_bridge.rmapi_client.subprocess.run", return_value=_ok()) as m:
        rmapi_client.put(str(pdf), "/Obsidian")
        put_calls = [call for call in m.call_args_list if call.args[0][1] == "put"]
        assert put_calls
        cmd = put_calls[0].args[0]
        assert "--content-only" not in cmd


# --- Item 7: rmapi resolution fallback ---


def test_resolve_rmapi_env(tmp_path, monkeypatch):
    """Item 7: ORB_RMAPI_BIN env takes priority."""
    fake_bin = tmp_path / "fake_rmapi"
    fake_bin.write_text("#!/bin/sh\necho rmapi")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("ORB_RMAPI_BIN", str(fake_bin))
    assert rmapi_client.resolve_rmapi() == str(fake_bin)


def test_resolve_rmapi_config(tmp_path, monkeypatch):
    """Item 7: config.rmapi.path is step 2."""
    fake_bin = tmp_path / "cfg_rmapi"
    fake_bin.write_text("#!/bin/sh\necho rmapi")
    fake_bin.chmod(0o755)
    monkeypatch.delenv("ORB_RMAPI_BIN", raising=False)
    with patch("obsidian_rm_bridge.config.get", return_value=str(fake_bin)):
        result = rmapi_client.resolve_rmapi()
    assert result == str(fake_bin)


def test_resolve_rmapi_which(monkeypatch):
    """Item 7: shutil.which is step 3."""
    monkeypatch.delenv("ORB_RMAPI_BIN", raising=False)
    with patch("obsidian_rm_bridge.rmapi_client.shutil.which", return_value="/usr/bin/rmapi"), \
         patch("obsidian_rm_bridge.config.get", return_value=""):
        assert rmapi_client.resolve_rmapi() == "/usr/bin/rmapi"


def test_resolve_rmapi_fallback(tmp_path, monkeypatch):
    """Item 7: ~/.local/bin/rmapi is step 4."""
    monkeypatch.delenv("ORB_RMAPI_BIN", raising=False)
    fake_bin = tmp_path / ".local" / "bin" / "rmapi"
    fake_bin.parent.mkdir(parents=True)
    fake_bin.write_text("#!/bin/sh\necho rmapi")
    fake_bin.chmod(0o755)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    with patch("obsidian_rm_bridge.rmapi_client.shutil.which", return_value=None), \
         patch("obsidian_rm_bridge.config.get", return_value=""):
        assert rmapi_client.resolve_rmapi() == str(fake_bin)


def test_resolve_rmapi_not_found(monkeypatch):
    """Item 7: returns None when nothing is found."""
    monkeypatch.delenv("ORB_RMAPI_BIN", raising=False)
    with patch("obsidian_rm_bridge.rmapi_client.shutil.which", return_value=None), \
         patch("obsidian_rm_bridge.config.get", return_value=""), \
         patch("pathlib.Path.home", return_value=Path("/nonexistent_home")):
        assert rmapi_client.resolve_rmapi() is None