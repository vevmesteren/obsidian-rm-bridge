"""Tests for config loading (TOML + env overrides) — DC-3."""

from __future__ import annotations

import sys

import pytest

from obsidian_rm_bridge import config as cfg


def test_defaults_when_no_file(tmp_config):
    loaded = cfg.load_config()
    assert loaded["remarkable"]["folder"] == "/Obsidian"
    assert loaded["vision"]["model"] == "z-ai/glm-4.5v"
    assert loaded["vault"]["path"] == "~/Documents/Obsidian"


def test_set_then_show_round_trip(tmp_config):
    cfg.set("remarkable.folder", "/MyNotes")
    cfg.set("vision.model", "gpt-4o")
    shown = cfg.show()
    assert "remarkable" in shown
    assert "/MyNotes" in shown
    assert "gpt-4o" in shown
    # persisted to disk
    assert cfg.get("remarkable.folder") == "/MyNotes"


def test_flat_alias_set(tmp_config):
    cfg.set("rm_folder", "/Vault")
    assert cfg.get("rm_folder") == "/Vault"
    assert cfg.get("remarkable.folder") == "/Vault"


def test_env_overrides_file(tmp_config, monkeypatch):
    cfg.set("remarkable.folder", "/FromFile")
    cfg.set("vision.model", "from-file-model")
    monkeypatch.setenv("ORB_RM_FOLDER", "/FromEnv")
    monkeypatch.setenv("ORB_VISION_MODEL", "env-model")
    loaded = cfg.load_config()
    assert loaded["remarkable"]["folder"] == "/FromEnv"
    assert loaded["vision"]["model"] == "env-model"
    # get() reflects the override too
    assert cfg.get("remarkable.folder") == "/FromEnv"


def test_env_api_key_override(tmp_config, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-key-ABCD")
    assert cfg.get("vision.openrouter_api_key") == "dummy-key-ABCD"


def test_show_masks_api_key(tmp_config, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "topsecret-ABCD")
    shown = cfg.show()
    assert "topsecret-ABCD" not in shown  # full key never printed
    assert "ABCD" in shown  # last 4 retained for confirmation


def test_init_config_writes_defaults(tmp_config):
    path = cfg.init_config()
    assert path.is_file()
    loaded = cfg.load_config()
    assert loaded["remarkable"]["folder"] == "/Obsidian"


def test_init_config_does_not_overwrite_existing(tmp_config):
    """Copilot #3: init_config must be idempotent — existing config is preserved."""
    cfg.set("remarkable.folder", "/Custom")
    cfg.set("vision.model", "custom-model")
    cfg.init_config()  # should NOT overwrite
    assert cfg.get("remarkable.folder") == "/Custom"
    assert cfg.get("vision.model") == "custom-model"


@pytest.mark.skipif(sys.platform == "win32", reason="Unix file permissions")
def test_config_file_permissions_are_owner_only(tmp_config):
    """Copilot R2-1: config file must have 0600 permissions to protect API keys."""
    import os
    cfg.set("vision.openrouter_api_key", "sk-secret")
    cfg_path = cfg.config_path()
    mode = oct(os.stat(cfg_path).st_mode & 0o777)
    assert mode == "0o600", f"config file is {mode}, expected 0o600"


@pytest.mark.skipif(sys.platform == "win32", reason="Unix file permissions")
def test_init_config_permissions_are_owner_only(tmp_config):
    """Adversarial I4: init_config must also create with 0600."""
    import os
    cfg.init_config()
    cfg_path = cfg.config_path()
    mode = oct(os.stat(cfg_path).st_mode & 0o777)
    assert mode == "0o600", f"config file is {mode}, expected 0o600"


def test_numeric_pdf_coercion(tmp_config):
    cfg.set("pdf.font_size", "18")
    assert cfg.get("pdf.font_size") == 18
    assert isinstance(cfg.get("pdf.font_size"), int)


def test_no_hardcoded_hermes_or_veviki_paths():
    """DC-3: no veviki/Hermes paths in the defaults."""
    flat = repr(cfg.DEFAULTS)
    assert "hermes" not in flat.lower()
    assert "veviki" not in flat.lower()
    assert "/Wiki" not in flat  # decoupled from the old hardcoded folder