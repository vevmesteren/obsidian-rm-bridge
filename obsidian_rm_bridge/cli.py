"""``ormb`` CLI entry point for obsidian-rm-bridge.

argparse-based subcommands (no Click/Typer dependency — keeps the install lean;
``ormb --help`` lists every command). All commands read config from
:mod:`config` so nothing is hardcoded (DC-3).
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

from . import __version__, publisher, retriever, rmapi_client
from . import config as cfg
from .config import resolve_key
from .utils import expand_user_path

__all__ = ["build_parser", "main"]


# --- helpers ---------------------------------------------------------------


def _eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def _emit_json(ok: bool, code: str, message: str, data=None) -> None:
    """Print a JSON result envelope to stdout (ARB item 1)."""
    print(json.dumps({"ok": ok, "code": code, "message": message, "data": data}))


def _classify_error(e: Exception) -> str:
    """Map an exception to a standardized error code (ARB item 1).

    Handles the full ARB error-code spec:
    - ``note_not_found`` — missing source note
    - ``rmapi_missing`` / ``not_paired`` / ``cli_error`` — rmapi failures
    - ``chromium_missing`` — Playwright/Chromium unavailable
    - ``key_missing`` — OpenRouter API key not set
    - ``rate_limited`` — HTTP 429 / rate limit
    - ``vision_failed`` — all pages failed transcription
    """
    from .rmapi_client import RmapiError

    if isinstance(e, FileNotFoundError):
        return "note_not_found"
    msg = str(e).lower()
    # rmapi errors first (RmapiError is a RuntimeError subclass).
    if isinstance(e, RmapiError):
        if "binary not found" in msg:
            return "rmapi_missing"
        if "not paired" in msg or "token" in msg or "unauthorized" in msg:
            return "not_paired"
        return "cli_error"
    # rate_limited: check BEFORE vision_failed (grok F5) — 429s can surface
    # inside a "failed transcription" RuntimeError, so check rate first.
    if "429" in msg or "rate limit" in msg or "rate-limited" in msg:
        return "rate_limited"
    # key_missing: vision client raises RuntimeError("OPENROUTER_API_KEY is not set").
    # Match on "api_key" (underscore) or "openrouter" + "not set" (grok F3).
    if isinstance(e, RuntimeError) and ("api_key" in msg or "api key" in msg) and "not set" in msg:
        return "key_missing"
    if isinstance(e, RuntimeError) and "openrouter" in msg and "not set" in msg:
        return "key_missing"
    # vision_failed: transcribe_pages raises when every page failed.
    if isinstance(e, RuntimeError) and "failed transcription" in msg:
        return "vision_failed"
    # chromium_missing: Playwright Error is not RuntimeError (grok F4).
    # Check message content regardless of exception type.
    if "executable" in msg or "chromium" in msg or "browser" in msg or "playwright" in msg:
        return "chromium_missing"
    return "cli_error"


def _doc_exists_in_listing(listing: str, name: str) -> bool:
    """Check if a document name exists in rmapi ls output."""
    for ln in listing.splitlines():
        ln = ln.strip()
        if not ln or not ln.startswith("[f]"):
            continue
        doc_name = ln[3:].lstrip("\t ").strip()
        if doc_name == name:
            return True
    return False


def _setup_publish_parser(p):
    p.add_argument("path", help="Path to a .md file or a folder of .md files")
    p.add_argument("--folder", action="store_true", help="Publish all .md in the folder as one combined PDF")
    p.add_argument("--rm-folder", default=None, help="reMarkable destination folder (overrides config)")
    p.add_argument("--dry-run", action="store_true", help="Render the PDF but skip the rmapi upload")
    p.add_argument("--json", action="store_true", help="Emit a JSON result envelope on stdout")
    p.add_argument("--on-exists", choices=["fail", "content-only"], default="fail",
                   help="Behavior when the document already exists (default: fail)")
    p.add_argument("--vault", default=None, help="Vault root path (overrides config; enables containment check)")


def _setup_pull_parser(p):
    p.add_argument("page_name", nargs="?", help="Page name on reMarkable (e.g. my-page)")
    p.add_argument("--md", dest="md_path", default=None, help="Source markdown file to append annotations to")
    p.add_argument("--all", dest="pull_all", action="store_true", help="Pull all annotated pages from the reMarkable folder")
    p.add_argument("--rm-folder", default=None, help="reMarkable source folder (overrides config)")
    p.add_argument("--json", action="store_true", help="Emit a JSON result envelope on stdout")
    p.add_argument("--emit", choices=["json"], default=None,
                   help="Output format: 'json' returns sections without writing to disk")
    p.add_argument("--info", action="store_true",
                   help="Download + render only; return page counts without calling vision (for the consent modal). Mutually exclusive with --emit/--all.")
    p.add_argument("--vault", default=None, help="Vault root path (overrides config; enables containment check)")


def _setup_config_parser(p):
    sub = p.add_subparsers(dest="config_cmd", required=True)
    s = sub.add_parser("set", help="Set a configuration option")
    s.add_argument("key", help="Config key (dotted, e.g. vision.model) or flat alias (e.g. vision_model)")
    s.add_argument("value", help="Value to set")
    sub.add_parser("show", help="Show the resolved configuration (API key masked)")
    sub.add_parser("init", help="Write the default config to disk")
    sub.add_parser("set-key", help="Set the OpenRouter API key from stdin (not visible in argv)")


def _setup_setup_parser(p):
    p.add_argument("--rmapi", action="store_true", help="Download and install the rmapi binary instead of the Playwright browser")


def _setup_ls_parser(p):
    p.add_argument("folder", nargs="?", default=None, help="reMarkable folder to list (default: config remarkable.folder)")


def _setup_rm_parser(p):
    p.add_argument("page_name", help="Page name/path on reMarkable to delete")


def _setup_doctor_parser(p):
    p.add_argument("--json", action="store_true", help="Emit a JSON health check")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ormb",
        description=(
            "obsidian-rm-bridge — publish Obsidian markdown to reMarkable as PDFs, "
            "then pull handwritten annotations back into your vault."
        ),
    )
    parser.add_argument("--version", action="version", version=f"ormb {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    _setup_publish_parser(sub.add_parser("publish", help="Publish a markdown page or folder to reMarkable as a PDF"))
    _setup_pull_parser(sub.add_parser("pull", help="Download, transcribe annotations, and append to source .md"))
    _setup_config_parser(sub.add_parser("config", help="Manage configuration (set/show/init/set-key)"))
    _setup_setup_parser(sub.add_parser("setup", help="Install the Playwright browser, or --rmapi to install rmapi"))
    sub.add_parser("pair", help="Pair rmapi with reMarkable (prompts for one-time code)")
    _setup_ls_parser(sub.add_parser("ls", help="List files on reMarkable"))
    _setup_rm_parser(sub.add_parser("rm", help="Delete a file on reMarkable"))
    _setup_doctor_parser(sub.add_parser("doctor", help="Health check for dependencies and configuration"))

    return parser


# --- command handlers -----------------------------------------------------


def cmd_publish(args) -> int:
    # Item 6: use expand_user_path (no expandvars) for argv paths.
    path = expand_user_path(args.path)
    # Item 5: --vault takes precedence over config.vault.path.
    vault_root = None
    if args.vault:
        vault_root = expand_user_path(args.vault).resolve()
    # Resolve relative paths against vault root (issue #4).
    if not path.is_absolute():
        vr = args.vault or cfg.get("vault.path")
        if vr:
            path = Path(os.path.expanduser(str(vr))) / path
    # Item 11: containment check when --vault is provided.
    if vault_root is not None:
        resolved = path.resolve()
        if not resolved.is_relative_to(vault_root):
            if args.json:
                _emit_json(False, "path_containment",
                           f"Path resolves outside vault: {resolved}", None)
            else:
                _eprint(f"Error: path resolves outside vault: {resolved}")
            return 1

    rm_folder = args.rm_folder or cfg.get("remarkable.folder")
    name = path.stem if path.is_file() else path.name
    content_only = args.on_exists == "content-only"

    # Item 4 / cold review #4: --on-exists fail check runs regardless of --json.
    if args.on_exists == "fail" and not args.dry_run:
        try:
            listing = rmapi_client.ls(rm_folder)
            if _doc_exists_in_listing(listing, name):
                msg = (f"Document '{name}' already exists in {rm_folder}. "
                       f"Use --on-exists content-only to replace content "
                       f"while preserving annotations.")
                if args.json:
                    _emit_json(False, "doc_exists", msg, None)
                else:
                    _eprint(f"Error: {msg}")
                return 1
        except Exception as e:  # noqa: BLE001 — log but don't block publish
            _eprint(f"Warning: could not check for existing document: {e}")

    try:
        if args.folder:
            if not path.is_dir():
                _eprint(f"Error: --folder requires a directory, not a file: {path}")
                return 2
            dest, pages = publisher.publish_folder(path, rm_folder,
                                            dry_run=args.dry_run, content_only=content_only,
                                            vault_root=str(vault_root) if vault_root else None)
        elif path.is_dir():
            dest, pages = publisher.publish_folder(path, rm_folder,
                                            dry_run=args.dry_run, content_only=content_only,
                                            vault_root=str(vault_root) if vault_root else None)
        elif path.is_file():
            dest, pages = publisher.publish_page(path, rm_folder,
                                          dry_run=args.dry_run, content_only=content_only,
                                          vault_root=str(vault_root) if vault_root else None)
        else:
            if args.json:
                _emit_json(False, "note_not_found", f"File not found: {path}", None)
            else:
                _eprint(f"Error: {path} is not a file or folder")
            return 2
    except Exception as e:  # noqa: BLE001
        if args.json:
            _emit_json(False, _classify_error(e), str(e), None)
        else:
            _eprint(f"Error: {e}")
        return 1

    if args.json:
        _emit_json(True, "published", f"Published '{name}' to {dest}",
                   {"name": name, "folder": rm_folder, "dest": dest, "pages": pages})
    return 0


def cmd_pull(args) -> int:
    # Item 5: --vault takes precedence over config.vault.path.
    vault_root = None
    if args.vault:
        vault_root = expand_user_path(args.vault).resolve()

    # Phase 5c AC-5: --info is mutually exclusive with --emit and --all.
    if args.info:
        if args.emit == "json":
            if args.json:
                _emit_json(False, "cli_error",
                           "pull --info and --emit json are mutually exclusive", None)
            else:
                _eprint("Error: pull --info and --emit json are mutually exclusive.")
            return 1
        if args.pull_all:
            if args.json:
                _emit_json(False, "cli_error",
                           "pull --info and --all are mutually exclusive", None)
            else:
                _eprint("Error: pull --info and --all are mutually exclusive.")
            return 1

    if args.pull_all:
        if args.emit == "json":
            if args.json:
                _emit_json(False, "cli_error",
                           "pull --all --emit json is not supported (use pull <page> --emit json)", None)
            else:
                _eprint("Error: pull --all --emit json is not supported. Use 'pull <page> --emit json'.")
            return 1
        rm_folder = args.rm_folder or cfg.get("remarkable.folder")
        vault = args.vault or cfg.get("vault.path")
        listing = rmapi_client.ls(rm_folder)
        _eprint(listing)
        names = []
        for ln in listing.splitlines():
            ln = ln.strip()
            if not ln or not ln.startswith("[f]"):
                continue
            name = ln[3:].lstrip("\t ").strip()
            if name:
                names.append(name)
        # Item 5/7: use expand_user_path (no expandvars) for vault paths.
        vault_resolved = expand_user_path(str(vault)).resolve() if vault else None
        # Cold review #2: containment check on resolved md paths in pull --all.
        if vault_root is not None:
            for name in names:
                md = (vault_resolved or Path("")) / f"{name}.md"
                if not md.resolve().is_relative_to(vault_root):
                    if args.json:
                        _emit_json(False, "path_containment",
                                   f"Path resolves outside vault: {md.resolve()}", None)
                    else:
                        _eprint(f"Error: path resolves outside vault: {md.resolve()}")
                    return 1
        results = []
        for name in names:
            md = vault_resolved / f"{name}.md" if vault_resolved else None
            if md is not None and md.is_file():
                try:
                    retriever.retrieve(name, md, rm_folder=rm_folder)
                    results.append({"page_name": name, "md_path": str(md)})
                except Exception as e:  # noqa: BLE001
                    if args.json:
                        _emit_json(False, _classify_error(e), str(e), None)
                    else:
                        _eprint(f"Error: {e}")
                    return 1
            else:
                _eprint(f"  skipping {name}: no source .md at {md}")
        # Cold review #3: pull --all --json emits a JSON success envelope.
        if args.json:
            _emit_json(True, "transcribed",
                       f"Pulled {len(results)} page(s) from {rm_folder}",
                       {"pages": len(results), "files": results})
        return 0

    if not args.page_name:
        _eprint("Error: pull requires a <page-name> (or --all)")
        return 2

    md_path = args.md_path
    if md_path is None:
        vault = args.vault or cfg.get("vault.path")
        md_path = str(expand_user_path(str(vault)).resolve() / f"{args.page_name}.md") if vault else f"{args.page_name}.md"
    else:
        # Item 6: use expand_user_path (no expandvars) for argv paths.
        md_path = str(expand_user_path(md_path))
        if not Path(md_path).is_absolute():
            vault = args.vault or cfg.get("vault.path")
            if vault:
                # Item 7: use expand_user_path (no expandvars) for vault paths.
                md_path = str(expand_user_path(str(vault)) / md_path)
    # Item 11: containment check when --vault is provided.
    if vault_root is not None:
        resolved = Path(md_path).resolve()
        if not resolved.is_relative_to(vault_root):
            if args.json:
                _emit_json(False, "path_containment",
                           f"Path resolves outside vault: {resolved}", None)
            else:
                _eprint(f"Error: path resolves outside vault: {resolved}")
            return 1

    # Phase 5c AC-5: --info — page count without calling vision (for the
    # consent modal). Requires a page_name (no --all). Returns total_pages
    # and annotated_pages (= total_pages at this stage).
    if args.info:
        if not args.page_name:
            _eprint("Error: pull --info requires a <page-name>")
            return 2
        try:
            info = retriever.retrieve_info(
                args.page_name, rm_folder=args.rm_folder)
        except Exception as e:  # noqa: BLE001
            if args.json:
                _emit_json(False, _classify_error(e), str(e), None)
            else:
                _eprint(f"Error: {e}")
            return 1
        if args.json:
            _emit_json(True, "info",
                       f"{info['total_pages']} page(s) on {args.page_name}",
                       info)
        else:
            print(json.dumps(info, indent=2))
        return 0

    # Item 3: --emit json returns sections without writing to disk.
    if args.emit == "json":
        try:
            result = retriever.retrieve_to_json(
                args.page_name, rm_folder=args.rm_folder)
        except Exception as e:  # noqa: BLE001
            if args.json:
                _emit_json(False, _classify_error(e), str(e), None)
            else:
                _eprint(f"Error: {e}")
            return 1
        if args.json:
            _emit_json(True, "transcribed",
                       f"Transcribed {result['annotated_pages']} page(s) from {args.page_name}",
                       result)
        else:
            print(json.dumps(result, indent=2))
        return 0

    try:
        retriever.retrieve(args.page_name, md_path, rm_folder=args.rm_folder)
    except Exception as e:  # noqa: BLE001
        if args.json:
            _emit_json(False, _classify_error(e), str(e), None)
        else:
            _eprint(f"Error: {e}")
        return 1

    if args.json:
        _emit_json(True, "transcribed",
                   f"Transcribed annotations from {args.page_name} into {md_path}",
                   {"page_name": args.page_name, "md_path": md_path})
    return 0


def cmd_config(args) -> int:
    if args.config_cmd == "set-key":
        # Item 10: read API key from stdin (or getpass if TTY).
        key = sys.stdin.readline().strip()
        if not key and sys.stdin.isatty():
            key = getpass.getpass("OpenRouter API key: ")
        if not key:
            _eprint("Error: no key provided on stdin.")
            return 1
        cfg.set("vision.openrouter_api_key", key)
        _eprint("API key set. Use 'ormb config show' to verify.")
        return 0
    if args.config_cmd == "set":
        # Item 10: deprecation warning for legacy openrouter_api_key set.
        resolved = resolve_key(args.key)
        if resolved == "vision.openrouter_api_key":
            _eprint("Warning: 'config set openrouter_api_key' is deprecated. "
                    "Use 'config set-key' instead (reads from stdin, "
                    "key not visible in argv).")
        cfg.set(args.key, args.value)
        # Mask secret values in confirmation output (Copilot #1).
        display = cfg._mask(str(args.value)) if "api_key" in resolved else args.value
        _eprint(f"Set {args.key} = {display}")
    elif args.config_cmd == "show":
        print(cfg.show())
    elif args.config_cmd == "init":
        path = cfg.init_config()
        _eprint(f"Wrote default config to {path}")
    return 0


# Pinned rmapi release tag (Phase 5c AC-6). Supply-chain hardening: instead
# of following ``releases/latest`` (which can move unexpectedly), we pin a
# specific release and verify the downloaded archive's sha256 against the
# hashes recorded in the GitHub release assets. Update this constant (and
# RMAPI_SHA256 below) when bumping rmapi.
RMAPI_VERSION = "v0.0.35"
# sha256 digests of each release asset (from the GitHub release's `digest`
# field, recorded at release time). Keyed by asset filename.
RMAPI_SHA256: dict[str, str] = {
    "rmapi-linux-amd64.tar.gz": "117616151d11937446ead6972b0934f97155443087f8406141db38fd1ac8fb25",
    "rmapi-linux-arm64.tar.gz": "645c170d8119b4dcb652cf79612e362fcb032dc0e5869ff520eec1324da39637",
    "rmapi-macos-arm64.zip": "fb55b6c782b83dc0ccbb236359d738727c4c600378feae920fcab505862f624a",
    "rmapi-macos-intel.zip": "1afc2c4d73ddde60e22e0ff8d2bc737450dfcaeaa723eb6a3b863ac96cb2102c",
    "rmapi-win-arm64.zip": "a8c540f72a17228b2a5027d8c26332db9718de3d049742788c0cdd9e30d20268",
    "rmapi-win64.zip": "f8132c68044f054b2cca14c30d4525ea0fd78b2af175998d2aad5b3c8afcb05b",
}


def _rmapi_asset_url() -> tuple[str, str]:
    """Return ``(download_url, extracted_binary_name)`` for this platform.

    Phase 5c AC-6: the URL targets a pinned release tag (RMAPI_VERSION)
    rather than ``releases/latest``, so a malicious/compromised upstream
    release can't silently change what gets installed. The archive is
    sha256-verified after download in :func:`cmd_setup`.
    """
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux":
        arch = "arm64" if machine in ("aarch64", "arm64") else "amd64"
        asset = f"rmapi-linux-{arch}.tar.gz"
        return (
            f"https://github.com/ddvk/rmapi/releases/download/{RMAPI_VERSION}/{asset}",
            "rmapi",
        )
    if system == "darwin":
        # ddvk/rmapi publishes macOS assets as ZIP, not tar.gz (Copilot #5).
        # Asset names: rmapi-macos-arm64.zip, rmapi-macos-intel.zip
        arch = "arm64" if machine == "arm64" else "intel"
        asset = f"rmapi-macos-{arch}.zip"
        return (
            f"https://github.com/ddvk/rmapi/releases/download/{RMAPI_VERSION}/{asset}",
            "rmapi",
        )
    if system in ("windows", "win32"):
        # ddvk/rmapi publishes Windows assets as ZIP (Copilot #5).
        # Include ARM64 support (adversarial I2).
        arch = "win-arm64" if machine in ("arm64", "aarch64") else "win64"
        asset = f"rmapi-{arch}.zip"
        return (
            f"https://github.com/ddvk/rmapi/releases/download/{RMAPI_VERSION}/{asset}",
            "rmapi.exe",
        )
    raise RuntimeError(f"unsupported platform: {system} {machine}")


def cmd_setup(args) -> int:
    if args.rmapi:
        import hashlib as _hashlib

        url, bin_name = _rmapi_asset_url()
        asset_name = Path(url).name
        expected_sha = RMAPI_SHA256.get(asset_name)
        dest = Path.home() / ".local" / "bin"
        dest.mkdir(parents=True, exist_ok=True)
        _eprint(f"Downloading rmapi {RMAPI_VERSION} from {url} ...")
        import requests

        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / asset_name
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
            archive.write_bytes(resp.content)
            # Phase 5c AC-6: verify the sha256 of the downloaded archive before
            # extracting. Reject on mismatch so a tampered/compromised asset
            # can't reach the install dir.
            actual_sha = _hashlib.sha256(archive.read_bytes()).hexdigest()
            if expected_sha is None:
                raise RuntimeError(
                    f"No sha256 recorded for rmapi asset '{asset_name}' at "
                    f"{RMAPI_VERSION}. Refusing to install an unverified binary."
                )
            if actual_sha != expected_sha:
                raise RuntimeError(
                    f"rmapi archive sha256 mismatch for '{asset_name}': "
                    f"expected {expected_sha}, got {actual_sha}. "
                    f"Refusing to install (possible tampering or wrong release)."
                )
            _eprint(f"sha256 verified: {actual_sha}")
            if archive.suffix == ".zip":
                with zipfile.ZipFile(archive) as z:
                    z.extractall(tmp)
            else:
                with tarfile.open(archive) as t:
                    # Use filter="data" for path-traversal protection (adversarial I8).
                    try:
                        t.extractall(tmp, filter="data")
                    except TypeError:
                        t.extractall(tmp)
            src = Path(tmp) / bin_name
            shutil.copy2(src, dest / bin_name)
            os.chmod(dest / bin_name, 0o755)
        _eprint(f"Installed rmapi {RMAPI_VERSION} to {dest / bin_name}")
        _eprint("Ensure that directory is on your PATH.")
        return 0
    _eprint("Installing Playwright Chromium browser...")
    # Install system dependencies first (Linux only — requires sudo).
    # Without these, Chromium crashes with missing shared libraries (issue #4).
    if sys.platform.startswith("linux"):
        _eprint("Installing system dependencies for Chromium (requires sudo)...")
        deps_rc = subprocess.call(
            ["sudo", sys.executable, "-m", "playwright", "install-deps", "chromium"],
        )
        if deps_rc != 0:
            _eprint(
                "Warning: could not install system dependencies. "
                f"Run: sudo {sys.executable} -m playwright install-deps chromium"
            )
    return subprocess.call([sys.executable, "-m", "playwright", "install", "chromium"])


def cmd_doctor(args) -> int:
    """Health check for dependencies and configuration (ARB item 2)."""
    errors: list[str] = []

    # rmapi
    rmapi_path = rmapi_client.resolve_rmapi()
    rmapi_found = rmapi_path is not None
    rmapi_version = ""
    if rmapi_found:
        try:
            result = subprocess.run(
                [rmapi_path, "--version"], check=False, capture_output=True, text=True, timeout=10)
            rmapi_version = (result.stdout or result.stderr or "").strip()
        except Exception:  # noqa: BLE001
            rmapi_version = "unknown"
    else:
        errors.append("rmapi binary not found")

    # chromium
    chromium_status = "ok"
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            b.close()
    except Exception as e:  # noqa: BLE001
        msg = str(e).lower()
        if "executable" in msg or "not found" in msg:
            chromium_status = "missing"
        else:
            chromium_status = "missing-deps"
        errors.append(f"Chromium: {chromium_status}")

    # vault
    vault_path = cfg.get("vault.path")
    vault_status = "reachable"
    if vault_path:
        vp = Path(os.path.expanduser(str(vault_path)))
        if vp.is_dir():
            vault_status = "reachable"
        else:
            vault_status = "not_found"
            errors.append(f"Vault path not found: {vp}")
    else:
        vault_status = "not_set"
        errors.append("vault.path not configured")

    # paired — rmapi stores its config at ~/.config/rmapi/rmapi.conf (XDG)
    # or ~/.rmapi (legacy). Check both.
    rmapi_xdg = Path.home() / ".config" / "rmapi" / "rmapi.conf"
    rmapi_legacy = Path.home() / ".rmapi"
    paired = rmapi_xdg.exists() or rmapi_legacy.exists()
    if not paired:
        errors.append("reMarkable not paired (run 'ormb pair')")

    # key_present
    key = os.environ.get("OPENROUTER_API_KEY", "") or str(cfg.get("vision.openrouter_api_key") or "")
    key_present = bool(key)
    if not key_present:
        errors.append("OPENROUTER_API_KEY not set")

    report = {
        "ok": len(errors) == 0,
        "version": __version__,
        "schema_version": 1,
        "rmapi": {"path": rmapi_path or "", "version": rmapi_version, "found": rmapi_found},
        "chromium": chromium_status,
        "vault": vault_status,
        "paired": paired,
        "key_present": key_present,
        "errors": errors,
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _eprint(f"ormb {__version__} (schema {report['schema_version']})")
        _eprint(f"  rmapi:   {'found' if rmapi_found else 'MISSING'}"
                f"{f' ({rmapi_path})' if rmapi_path else ''}"
                f"{f' v{rmapi_version}' if rmapi_version else ''}")
        _eprint(f"  chromium: {chromium_status}")
        _eprint(f"  vault:    {vault_status}")
        _eprint(f"  paired:   {'yes' if paired else 'NO'}")
        _eprint(f"  api key:  {'present' if key_present else 'MISSING'}")
        if errors:
            _eprint(f"  errors ({len(errors)}):")
            for e in errors:
                _eprint(f"    - {e}")
        else:
            _eprint("  All checks passed.")
    return 0 if not errors else 1


def cmd_pair(args) -> int:
    if not rmapi_client.find_rmapi():
        _eprint("rmapi binary not found. Install it with: ormb setup --rmapi")
        return 1
    return rmapi_client.pair()


def cmd_ls(args) -> int:
    folder = args.folder or cfg.get("remarkable.folder")
    print(rmapi_client.ls(folder))
    return 0


def cmd_rm(args) -> int:
    # Resolve relative names against the configured folder (Copilot #2).
    # Absolute paths (starting with /) are used as-is.
    page = args.page_name
    if not page.startswith("/"):
        folder = str(cfg.get("remarkable.folder"))
        page = f"{folder.rstrip('/')}/{page}"
    rmapi_client.rm(page)
    _eprint(f"Deleted {page}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {
        "publish": cmd_publish,
        "pull": cmd_pull,
        "config": cmd_config,
        "setup": cmd_setup,
        "pair": cmd_pair,
        "ls": cmd_ls,
        "rm": cmd_rm,
        "doctor": cmd_doctor,
    }
    handler = handlers.get(args.command)
    if handler is None:  # pragma: no cover - argparse enforces choices
        parser.print_help()
        return 2
    try:
        return handler(args)
    except KeyboardInterrupt:
        _eprint("\nInterrupted.")
        return 130
    except Exception as e:  # noqa: BLE001 - surface a clean CLI error
        _eprint(f"Error: {e}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())