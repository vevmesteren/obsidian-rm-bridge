"""Configuration for obsidian-rm-bridge.

Config lives at ``~/.obsidian-rm-bridge/config.toml`` (nested TOML schema).
Environment variables override file values; defaults are used when neither is
set. Nothing here is hardcoded to a veviki or Hermes path — all paths come from
config or env vars (DC-3).
"""

from __future__ import annotations

import os
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

import tomli_w

__all__ = [
    "CONFIG_DIR",
    "CONFIG_PATH",
    "DEFAULTS",
    "ENV_OVERRIDES",
    "FLAT_ALIASES",
    "config_dir",
    "config_path",
    "get",
    "init_config",
    "load_config",
    "resolve_key",
    "set",
    "show",
]

# Default location — overridable via ORB_CONFIG_DIR / ORB_CONFIG_PATH env vars.
CONFIG_DIR = Path(os.environ.get("ORB_CONFIG_DIR", Path.home() / ".obsidian-rm-bridge"))
CONFIG_PATH = Path(os.environ.get("ORB_CONFIG_PATH", CONFIG_DIR / "config.toml"))

# Nested default schema. Values chosen to match the proven veviki bridge defaults,
# with the reMarkable folder decoupled from /Wiki -> /Obsidian (DC-3).
DEFAULTS: dict = {
    "vault": {"path": "~/Documents/Obsidian"},
    "remarkable": {"folder": "/Obsidian"},
    "vision": {
        "model": "z-ai/glm-4.5v",
        "cross_verify_model": "gpt-4o",
        "openrouter_api_key": "",
    },
    "pdf": {"font_size": 14, "font_family": "Georgia", "code_font_size": 12},
}

# Dotted config key -> environment variable that overrides it.
ENV_OVERRIDES: dict[str, str] = {
    "vault.path": "ORB_VAULT_PATH",
    "remarkable.folder": "ORB_RM_FOLDER",
    "vision.model": "ORB_VISION_MODEL",
    "vision.cross_verify_model": "ORB_VISION_CROSS_VERIFY_MODEL",
    "vision.openrouter_api_key": "OPENROUTER_API_KEY",
    "pdf.font_size": "ORB_PDF_FONT_SIZE",
    "pdf.font_family": "ORB_PDF_FONT_FAMILY",
    "pdf.code_font_size": "ORB_PDF_CODE_FONT_SIZE",
}

# Flat convenience aliases accepted by `ormb config set <key> <value>`.
# Lets the README quickstart (`ormb config set vault_path ...`) work alongside
# the dotted TOML schema.
FLAT_ALIASES: dict[str, str] = {
    "vault_path": "vault.path",
    "rm_folder": "remarkable.folder",
    "vision_model": "vision.model",
    "cross_verify_model": "vision.cross_verify_model",
    "openrouter_api_key": "vision.openrouter_api_key",
    "font_size": "pdf.font_size",
    "font_family": "pdf.font_family",
    "code_font_size": "pdf.code_font_size",
}


def config_dir() -> Path:
    """Resolved config directory (created on demand by the caller)."""
    return CONFIG_DIR


def config_path() -> Path:
    """Resolved config file path."""
    return CONFIG_PATH


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge ``override`` into a copy of ``base``."""
    out = {k: (v.copy() if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _read_toml(path: str | os.PathLike | None) -> dict:
    """Read TOML from ``path``; return ``{}`` if missing or unreadable."""
    if path is None:
        return {}
    p = Path(os.path.expandvars(os.path.expanduser(str(path))))
    if not p.is_file():
        return {}
    with p.open("rb") as f:
        return tomllib.load(f)


def _get_nested(data: dict, dotted: str):
    """Walk a dotted key into a nested dict; return ``None`` if absent."""
    cur: object = data
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _set_nested(data: dict, dotted: str, value) -> None:
    """Set a dotted key in a nested dict, creating intermediate dicts."""
    parts = dotted.split(".")
    cur = data
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def load_config(path: str | os.PathLike | None = None) -> dict:
    """Load resolved config: defaults <- TOML file <- environment overrides.

    ``path`` defaults to :func:`config_path`. This never raises for a missing
    file; it raises only on a malformed TOML.
    """
    if path is None:
        path = config_path()
    file_cfg = _read_toml(path)
    cfg = _deep_merge(DEFAULTS, file_cfg)
    # Apply env overrides on top.
    for dotted, env_var in ENV_OVERRIDES.items():
        val = os.environ.get(env_var)
        if val is not None and val != "":
            # Coerce numeric pdf settings.
            if dotted.startswith("pdf.") and dotted not in ("pdf.font_family",):
                try:
                    val = int(val)  # type: ignore[assignment]
                except ValueError:
                    pass
            _set_nested(cfg, dotted, val)
    return cfg


def resolve_key(key: str) -> str:
    """Resolve a user-supplied config key to its canonical dotted form.

    Accepts dotted keys (``vault.path``) and flat aliases (``vault_path``).
    """
    return FLAT_ALIASES.get(key, key)


def get(key: str, path: str | os.PathLike | None = None):
    """Return a single resolved config value by dotted key or flat alias."""
    cfg = load_config(path)
    return _get_nested(cfg, resolve_key(key))


def set(key: str, value: str, path: str | os.PathLike | None = None) -> None:
    """Set ``key`` (dotted or alias) to ``value`` in the TOML file, creating it.

    Numeric ``pdf.*`` keys are coerced to ``int``.
    """
    if path is None:
        path = config_path()
    p = Path(os.path.expandvars(os.path.expanduser(str(path))))
    p.parent.mkdir(parents=True, exist_ok=True)
    data = _read_toml(p)
    dotted = resolve_key(key)
    if dotted.startswith("pdf.") and dotted not in ("pdf.font_family",):
        try:
            value = int(value)  # type: ignore[assignment]
        except (ValueError, TypeError):
            pass
    _set_nested(data, dotted, value)
    with p.open("wb") as f:
        tomli_w.dump(data, f)


def _mask(secret: str) -> str:
    """Mask a secret for display, keeping the last 4 characters."""
    if not secret:
        return ""
    if len(secret) <= 4:
        return "***"
    return f"***{secret[-4:]}"


def show(path: str | os.PathLike | None = None) -> str:
    """Return the resolved config as TOML text, with the API key masked."""
    cfg = load_config(path)
    # Mask the API key for safe display.
    key = _get_nested(cfg, "vision.openrouter_api_key")
    if key:
        _set_nested(cfg, "vision.openrouter_api_key", _mask(str(key)))
    return tomli_w.dumps(cfg).strip()


def init_config(path: str | os.PathLike | None = None) -> Path:
    """Write the default config to disk (idempotent; overwrites nothing existing)."""
    if path is None:
        path = config_path()
    p = Path(os.path.expandvars(os.path.expanduser(str(path))))
    p.parent.mkdir(parents=True, exist_ok=True)
    # Use 'xb' (exclusive create) — fails if the file already exists (Copilot #3).
    # The docstring says "overwrites nothing existing"; the code must match.
    try:
        with p.open("xb") as f:
            tomli_w.dump(DEFAULTS, f)
    except FileExistsError:
        pass  # Idempotent: leave existing config untouched.
    return p