"""Smoke tests for the `ormb` CLI — argparse dispatch, config, help."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from obsidian_rm_bridge import cli

COMMANDS = ("publish", "pull", "config", "setup", "pair", "ls", "rm")


def test_help_lists_all_commands():
    text = cli.build_parser().format_help()
    for cmd in COMMANDS:
        assert cmd in text, f"`{cmd}` missing from --help"


def test_help_exits_zero():
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0


def test_version_exits_zero():
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0


def test_no_command_errors():
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    # required subparser missing -> exit 2
    assert exc.value.code == 2


def test_config_set_show_round_trip(tmp_config, capsys):
    assert cli.main(["config", "set", "remarkable.folder", "/MyNotes"]) == 0
    assert cli.main(["config", "show"]) == 0
    out = capsys.readouterr().out
    assert "/MyNotes" in out
    from obsidian_rm_bridge import config as cfg

    assert cfg.get("remarkable.folder") == "/MyNotes"


def test_config_set_flat_alias(tmp_config):
    assert cli.main(["config", "set", "rm_folder", "/Vault"]) == 0
    from obsidian_rm_bridge import config as cfg

    assert cfg.get("remarkable.folder") == "/Vault"


def test_config_init(tmp_config):
    assert cli.main(["config", "init"]) == 0
    from obsidian_rm_bridge import config as cfg

    assert cfg.config_path().is_file()


def test_ls_invokes_rmapi(tmp_config):
    with patch("obsidian_rm_bridge.cli.rmapi_client.ls", return_value="file1\nfile2\n") as m:
        assert cli.main(["ls"]) == 0
        m.assert_called_once()


def test_ls_with_folder_arg(tmp_config):
    with patch("obsidian_rm_bridge.cli.rmapi_client.ls", return_value="") as m:
        assert cli.main(["ls", "/Custom"]) == 0
        assert "/Custom" in m.call_args[0][0]


def test_rm_invokes_rmapi(tmp_config):
    with patch("obsidian_rm_bridge.cli.rmapi_client.rm") as m:
        assert cli.main(["rm", "page"]) == 0
        m.assert_called_once()
        assert "page" in m.call_args[0][0]


def test_rm_resolves_relative_against_configured_folder(tmp_config):
    """Copilot #2: `ormb rm my-page` should target /Obsidian/my-page, not /my-page."""
    cli.main(["config", "set", "remarkable.folder", "/MyNotes"])
    with patch("obsidian_rm_bridge.cli.rmapi_client.rm") as m:
        assert cli.main(["rm", "my-page"]) == 0
        path = m.call_args[0][0]
        assert path == "/MyNotes/my-page"


def test_rm_keeps_absolute_path(tmp_config):
    """Copilot #2: absolute paths (starting with /) are used as-is."""
    with patch("obsidian_rm_bridge.cli.rmapi_client.rm") as m:
        assert cli.main(["rm", "/Custom/page"]) == 0
        assert m.call_args[0][0] == "/Custom/page"


def test_pull_missing_page_name_errors(tmp_config):
    assert cli.main(["pull"]) == 2


def test_pull_invokes_retrieve(tmp_config):
    with patch("obsidian_rm_bridge.cli.retriever.retrieve") as m:
        assert cli.main(["pull", "page", "--md", "some.md"]) == 0
        m.assert_called_once()
        assert m.call_args[0][0] == "page"


def test_publish_missing_path_errors(tmp_config):
    assert cli.main(["publish", "/nonexistent/path.md"]) == 2


def test_config_set_masks_api_key(tmp_config, capsys):
    """Copilot #1: setting openrouter_api_key should mask the value in stderr."""
    assert cli.main(["config", "set", "vision.openrouter_api_key", "sk-or-v1-secret123"]) == 0
    err = capsys.readouterr().err
    assert "sk-or-v1-secret123" not in err
    assert "***" in err or "****" in err


def test_config_init_does_not_overwrite_existing(tmp_config):
    """Copilot #3: `config init` must not overwrite an existing config file."""
    from obsidian_rm_bridge import config as cfg

    cfg.set("remarkable.folder", "/MyCustom")
    cfg.set("vision.model", "custom-model")
    # init should be idempotent — existing settings preserved
    cfg.init_config()
    assert cfg.get("remarkable.folder") == "/MyCustom"
    assert cfg.get("vision.model") == "custom-model"


def test_env_overrides_in_cli(tmp_config, monkeypatch, tmp_path):
    """Config is fully overridable via env vars (acceptance criterion)."""
    md = tmp_path / "x.md"
    md.write_text("# x\n")
    monkeypatch.setenv("ORB_RM_FOLDER", "/EnvFolder")
    with patch("obsidian_rm_bridge.cli.publisher.publish_page", return_value="/EnvFolder/x") as m:
        assert cli.main(["publish", str(md)]) == 0
        # publish_page was called with the env-derived rm_folder
        assert m.call_args[0][1] == "/EnvFolder"


def test_pull_default_md_resolves_relative_vault(tmp_config, tmp_path, monkeypatch):
    """Copilot R3-1: with a relative vault.path, pull should resolve to absolute
    before passing to retrieve(), avoiding double-prefixing (adversarial W2)."""
    from pathlib import Path

    # Set up a genuinely relative vault.path (adversarial W2)
    from obsidian_rm_bridge import config as cfg
    vault_dir = tmp_path / "notes"
    vault_dir.mkdir()
    (vault_dir / "my-page.md").write_text("# My Page\n\nContent.\n")
    monkeypatch.chdir(tmp_path)
    cfg.set("vault.path", "notes")  # relative, not absolute

    with patch("obsidian_rm_bridge.cli.retriever.retrieve") as m_ret:
        cli.main(["pull", "my-page"])
        called_md = m_ret.call_args[0][1]
        called_path = Path(called_md)
        assert called_path.is_absolute()
        # Must resolve to tmp_path/notes/my-page.md, not notes/notes/my-page.md
        assert called_path.name == "my-page.md"
        assert "notes/notes" not in called_md