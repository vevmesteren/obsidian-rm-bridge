"""Smoke tests for the `ormb` CLI — argparse dispatch, config, help."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from obsidian_rm_bridge import cli

COMMANDS = ("publish", "pull", "config", "setup", "pair", "ls", "rm", "doctor")


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


def test_publish_resolves_relative_path_against_vault(tmp_config, tmp_path, monkeypatch):
    """Issue #4: `ormb publish concepts/arch.md` should resolve against vault.path,
    not the current working directory."""
    from pathlib import Path

    from obsidian_rm_bridge import config as cfg

    vault_dir = tmp_path / "veviki"
    vault_dir.mkdir()
    sub_dir = vault_dir / "concepts" / "architecture"
    sub_dir.mkdir(parents=True)
    md = sub_dir / "c4-system-landscape.md"
    md.write_text("# C4 Landscape\n\nContent.\n")
    cfg.set("vault.path", str(vault_dir))
    # CWD is NOT the vault
    other_dir = tmp_path / "obsidian-rm-bridge"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)
    with patch("obsidian_rm_bridge.cli.publisher.publish_page") as m_pub:
        assert cli.main(["publish", "concepts/architecture/c4-system-landscape.md"]) == 0
        called_path = Path(m_pub.call_args[0][0])
        assert called_path.is_absolute()
        assert called_path.name == "c4-system-landscape.md"
        assert "concepts" in str(called_path)
        assert "architecture" in str(called_path)


# --- Item 1: --json result envelope on publish/pull ---


def test_publish_json_success(tmp_config, tmp_path, capsys):
    """Item 1: publish --json emits a JSON success envelope on stdout."""
    md = tmp_path / "note.md"
    md.write_text("# Note\n")
    with patch("obsidian_rm_bridge.cli.publisher.publish_page", return_value="/Obsidian/note"):
        rc = cli.main(["publish", str(md), "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    import json
    env = json.loads(out)
    assert env["ok"] is True
    assert env["code"] == "published"
    assert "data" in env
    assert env["data"]["name"] == "note"


def test_publish_json_error_note_not_found(tmp_config, capsys):
    """Item 1: publish --json on missing file returns note_not_found error code."""
    rc = cli.main(["publish", "/nonexistent/path.md", "--json"])
    assert rc == 2
    out = capsys.readouterr().out
    import json
    env = json.loads(out)
    assert env["ok"] is False
    assert env["code"] == "note_not_found"


def test_publish_json_doc_exists(tmp_config, tmp_path, capsys):
    """Item 4: publish --json --on-exists fail returns doc_exists when doc already on reMarkable."""
    md = tmp_path / "note.md"
    md.write_text("# Note\n")
    listing = "[f]\tnote\n"
    with patch("obsidian_rm_bridge.cli.rmapi_client.ls", return_value=listing):
        rc = cli.main(["publish", str(md), "--json"])
    assert rc == 1
    import json
    env = json.loads(capsys.readouterr().out)
    assert env["ok"] is False
    assert env["code"] == "doc_exists"


def test_publish_doc_exists_without_json(tmp_config, tmp_path, capsys):
    """Cold review #4: doc_exists check runs even without --json (stderr + return 1)."""
    md = tmp_path / "note.md"
    md.write_text("# Note\n")
    listing = "[f]\tnote\n"
    with patch("obsidian_rm_bridge.cli.rmapi_client.ls", return_value=listing), \
         patch("obsidian_rm_bridge.cli.publisher.publish_page") as m_pub:
        rc = cli.main(["publish", str(md)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "already exists" in err
    m_pub.assert_not_called()


def test_publish_on_exists_content_only(tmp_config, tmp_path):
    """Item 4: --on-exists content-only passes content_only=True to publisher."""
    md = tmp_path / "note.md"
    md.write_text("# Note\n")
    with patch("obsidian_rm_bridge.cli.publisher.publish_page", return_value="/Obsidian/note") as m:
        cli.main(["publish", str(md), "--on-exists", "content-only"])
        assert m.call_args.kwargs["content_only"] is True


def test_pull_json_success(tmp_config, capsys):
    """Item 1: pull --json emits a JSON success envelope on stdout."""
    with patch("obsidian_rm_bridge.cli.retriever.retrieve") as m:
        rc = cli.main(["pull", "page", "--md", "some.md", "--json"])
    assert rc == 0
    m.assert_called_once()
    import json
    env = json.loads(capsys.readouterr().out)
    assert env["ok"] is True
    assert env["code"] == "pulled"


# --- Item 2: doctor --json ---


def test_doctor_json_returns_schema(tmp_config, capsys):
    """Item 2: doctor --json returns the required health-check schema."""
    with patch("obsidian_rm_bridge.cli.rmapi_client.resolve_rmapi", return_value=None):
        rc = cli.main(["doctor", "--json"])
    assert rc == 1  # errors present (rmapi missing, etc.)
    import json
    out = capsys.readouterr().out
    report = json.loads(out)
    assert "ok" in report
    assert "version" in report
    assert "schema_version" in report
    assert "rmapi" in report
    assert "path" in report["rmapi"]
    assert "found" in report["rmapi"]
    assert "chromium" in report
    assert "vault" in report
    assert "paired" in report
    assert "key_present" in report
    assert "errors" in report
    assert isinstance(report["errors"], list)


def test_doctor_human_readable(tmp_config, capsys):
    """Item 2: doctor (no flag) prints human-readable output to stderr."""
    with patch("obsidian_rm_bridge.cli.rmapi_client.resolve_rmapi", return_value=None):
        cli.main(["doctor"])
    err = capsys.readouterr().err
    assert "ormb" in err
    assert "rmapi" in err.lower()


# --- Item 3: pull --emit json ---


def test_pull_emit_json_returns_sections(tmp_config, capsys, tmp_path):
    """Item 3: pull --emit json returns sections without writing to disk."""
    md = tmp_path / "page.md"
    md.write_text("# Page\n")
    mock_result = {
        "sections": [{"page": 1, "text": "## Annotations from reMarkable\n\n- Note 1\n"}],
        "doc_id": "page",
        "total_pages": 3,
        "annotated_pages": 1,
    }
    with patch("obsidian_rm_bridge.cli.retriever.retrieve_to_json", return_value=mock_result) as m:
        rc = cli.main(["pull", "page", "--md", str(md), "--emit", "json", "--json"])
    assert rc == 0
    m.assert_called_once()
    import json
    env = json.loads(capsys.readouterr().out)
    assert env["ok"] is True
    assert env["code"] == "transcribed"
    assert env["data"]["sections"][0]["page"] == 1
    assert env["data"]["total_pages"] == 3


def test_pull_emit_json_no_file_write(tmp_config, tmp_path):
    """Item 3: pull --emit json must NOT write to the source .md file."""
    md = tmp_path / "page.md"
    md.write_text("# Original\n")
    original = md.read_text()
    mock_result = {"sections": [{"page": 1, "text": "annotated"}], "doc_id": "page", "total_pages": 1, "annotated_pages": 1}
    with patch("obsidian_rm_bridge.cli.retriever.retrieve_to_json", return_value=mock_result):
        cli.main(["pull", "page", "--md", str(md), "--emit", "json"])
    assert md.read_text() == original  # file untouched


# --- Item 5: --vault flag ---


def test_publish_vault_flag_precedence(tmp_config, tmp_path, monkeypatch):
    """Item 5: --vault takes precedence over config.vault.path."""
    from obsidian_rm_bridge import config as cfg
    cfg.set("vault.path", str(tmp_path / "config_vault"))
    vault_dir = tmp_path / "explicit_vault"
    vault_dir.mkdir()
    md = vault_dir / "note.md"
    md.write_text("# Note\n")
    # CWD is NOT the vault
    monkeypatch.chdir(tmp_path)
    with patch("obsidian_rm_bridge.cli.publisher.publish_page") as m:
        cli.main(["publish", "note.md", "--vault", str(vault_dir)])
        called_path = Path(m.call_args[0][0])
        assert called_path.is_absolute()
        assert called_path.name == "note.md"
        assert "explicit_vault" in str(called_path)


def test_pull_vault_flag_precedence(tmp_config, tmp_path, monkeypatch):
    """Item 5: --vault takes precedence over config for pull md resolution."""
    from obsidian_rm_bridge import config as cfg
    cfg.set("vault.path", str(tmp_path / "config_vault"))
    vault_dir = tmp_path / "explicit_vault"
    vault_dir.mkdir()
    (vault_dir / "page.md").write_text("# Page\n")
    monkeypatch.chdir(tmp_path)
    with patch("obsidian_rm_bridge.cli.retriever.retrieve") as m:
        cli.main(["pull", "page", "--vault", str(vault_dir)])
        called_md = Path(m.call_args[0][1])
        assert "explicit_vault" in str(called_md)


# --- Item 10: config set-key ---


def test_config_set_key_stdin(tmp_config, monkeypatch):
    """Item 10: config set-key reads the API key from stdin."""
    import io
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    test_key = "sk-or-v1-secret123"
    monkeypatch.setattr("sys.stdin", io.StringIO(test_key + "\n"))
    assert cli.main(["config", "set-key"]) == 0
    from obsidian_rm_bridge import config as cfg
    assert cfg.get("vision.openrouter_api_key") == test_key


def test_config_set_openrouter_deprecation(tmp_config, capsys):
    """Item 10: legacy 'config set openrouter_api_key' prints deprecation warning."""
    cli.main(["config", "set", "openrouter_api_key", "sk-secret"])
    err = capsys.readouterr().err
    assert "deprecated" in err.lower()
    assert "set-key" in err


# --- Item 11: --vault containment ---


def test_publish_vault_containment_violation(tmp_config, tmp_path, capsys):
    """Item 11: path outside --vault returns path_containment code."""
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n")
    rc = cli.main(["publish", str(outside), "--vault", str(vault_dir), "--json"])
    assert rc == 1
    import json
    env = json.loads(capsys.readouterr().out)
    assert env["ok"] is False
    assert env["code"] == "path_containment"


def test_pull_vault_containment_violation(tmp_config, tmp_path, capsys):
    """Item 11: --md outside --vault returns path_containment code."""
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n")
    rc = cli.main(["pull", "page", "--md", str(outside), "--vault", str(vault_dir), "--json"])
    assert rc == 1
    import json
    env = json.loads(capsys.readouterr().out)
    assert env["ok"] is False
    assert env["code"] == "path_containment"


def test_publish_vault_traversal_attempt(tmp_config, tmp_path, capsys):
    """Item 11: path traversal via ../ returns path_containment, no file opened."""
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    secret = tmp_path / "secret.md"
    secret.write_text("# Secret\n")
    monkeypatch_cwd = tmp_path / "cwd"
    monkeypatch_cwd.mkdir()
    import os
    old_cwd = os.getcwd()
    os.chdir(monkeypatch_cwd)
    try:
        rc = cli.main(["publish", "../secret.md", "--vault", str(vault_dir), "--json"])
    finally:
        os.chdir(old_cwd)
    assert rc == 1
    import json
    env = json.loads(capsys.readouterr().out)
    assert env["code"] == "path_containment"


# --- Item 6: expandvars removal on argv paths ---


def test_publish_dollar_sign_filename(tmp_config, tmp_path, monkeypatch):
    """Item 6: a filename containing $ must not have expandvars applied."""
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    md = vault_dir / "Budget $HOME.md"
    md.write_text("# Budget\n")
    monkeypatch.setenv("HOME", "/tmp/should_not_expand")
    with patch("obsidian_rm_bridge.cli.publisher.publish_page") as m:
        cli.main(["publish", "Budget $HOME.md", "--vault", str(vault_dir)])
        called_path = Path(m.call_args[0][0])
        assert "$HOME" in called_path.name  # $HOME NOT expanded


# --- Cold review: pull --all containment + JSON (#2, #3, #11) ---


def test_pull_all_json_emits_envelope(tmp_config, tmp_path, capsys):
    """Cold review #3: pull --all --json emits a JSON success envelope."""
    from obsidian_rm_bridge import config as cfg
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    (vault_dir / "alpha.md").write_text("# Alpha\n")
    (vault_dir / "beta.md").write_text("# Beta\n")
    cfg.set("vault.path", str(vault_dir))
    listing = "[f]\talpha\n[f]\tbeta\n"
    with patch("obsidian_rm_bridge.cli.rmapi_client.ls", return_value=listing), \
         patch("obsidian_rm_bridge.cli.retriever.retrieve") as m_ret:
        rc = cli.main(["pull", "--all", "--json"])
    assert rc == 0
    import json
    env = json.loads(capsys.readouterr().out)
    assert env["ok"] is True
    assert env["code"] == "transcribed"
    assert env["data"]["pages"] == 2
    assert m_ret.call_count == 2


def test_pull_all_containment_violation(tmp_config, tmp_path, capsys):
    """Cold review #2/#11: pull --all --vault with a malicious listing name
    (containing ``..``) that would resolve outside the vault returns
    path_containment and retrieves nothing."""
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir()
    # Plant an .md outside the vault that the traversal name would reach.
    (tmp_path / "secret.md").write_text("# Secret\n")
    from obsidian_rm_bridge import config as cfg
    cfg.set("vault.path", str(vault_dir))
    listing = "[f]\t../secret\n"  # malicious name with traversal
    with patch("obsidian_rm_bridge.cli.rmapi_client.ls", return_value=listing), \
         patch("obsidian_rm_bridge.cli.retriever.retrieve") as m_ret:
        rc = cli.main(["pull", "--all", "--vault", str(vault_dir), "--json"])
    assert rc == 1
    import json
    env = json.loads(capsys.readouterr().out)
    assert env["ok"] is False
    assert env["code"] == "path_containment"
    m_ret.assert_not_called()