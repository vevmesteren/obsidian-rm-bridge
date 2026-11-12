"""Shared fixtures and skip helpers for obsidian-rm-bridge tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the config module at an isolated temp dir/file for the test.

    Returns the config file path; tests can write TOML into it directly.
    """
    cfg_dir = tmp_path / "orb-config"
    cfg_dir.mkdir()
    cfg_file = cfg_dir / "config.toml"
    monkeypatch.setenv("ORB_CONFIG_DIR", str(cfg_dir))
    monkeypatch.setenv("ORB_CONFIG_PATH", str(cfg_file))
    # Re-import-sensitive: the config module reads these at import time for the
    # module-level constants, so also override the module attributes.
    from obsidian_rm_bridge import config as cfg_mod

    monkeypatch.setattr(cfg_mod, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(cfg_mod, "CONFIG_PATH", cfg_file)
    return cfg_file


def _chromium_available() -> bool:
    """True if a Playwright Chromium browser is installed locally."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:  # noqa: BLE001 - probing optional dependency
        return False
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            b.close()
        return True
    except Exception:  # noqa: BLE001 - browser may not be installed
        return False


requires_browser = pytest.mark.skipif(
    not _chromium_available(),
    reason="Playwright Chromium browser not installed (run: ormb setup)",
)