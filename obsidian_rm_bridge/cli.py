"""``ormb`` CLI entry point for obsidian-rm-bridge.

argparse-based subcommands (no Click/Typer dependency — keeps the install lean;
``ormb --help`` lists every command). All commands read config from
:mod:`config` so nothing is hardcoded (DC-3).
"""

from __future__ import annotations

import argparse
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

__all__ = ["build_parser", "main"]


# --- helpers ---------------------------------------------------------------


def _eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def _setup_publish_parser(p):
    p.add_argument("path", help="Path to a .md file or a folder of .md files")
    p.add_argument("--folder", action="store_true", help="Publish all .md in the folder as one combined PDF")
    p.add_argument("--rm-folder", default=None, help="reMarkable destination folder (overrides config)")
    p.add_argument("--dry-run", action="store_true", help="Render the PDF but skip the rmapi upload")


def _setup_pull_parser(p):
    p.add_argument("page_name", nargs="?", help="Page name on reMarkable (e.g. my-page)")
    p.add_argument("--md", dest="md_path", default=None, help="Source markdown file to append annotations to")
    p.add_argument("--all", dest="pull_all", action="store_true", help="Pull all annotated pages from the reMarkable folder")
    p.add_argument("--rm-folder", default=None, help="reMarkable source folder (overrides config)")


def _setup_config_parser(p):
    sub = p.add_subparsers(dest="config_cmd", required=True)
    s = sub.add_parser("set", help="Set a configuration option")
    s.add_argument("key", help="Config key (dotted, e.g. vision.model) or flat alias (e.g. vision_model)")
    s.add_argument("value", help="Value to set")
    sub.add_parser("show", help="Show the resolved configuration (API key masked)")
    sub.add_parser("init", help="Write the default config to disk")


def _setup_setup_parser(p):
    p.add_argument("--rmapi", action="store_true", help="Download and install the rmapi binary instead of the Playwright browser")


def _setup_ls_parser(p):
    p.add_argument("folder", nargs="?", default=None, help="reMarkable folder to list (default: config remarkable.folder)")


def _setup_rm_parser(p):
    p.add_argument("page_name", help="Page name/path on reMarkable to delete")


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
    _setup_config_parser(sub.add_parser("config", help="Manage configuration (set/show/init)"))
    _setup_setup_parser(sub.add_parser("setup", help="Install the Playwright browser, or --rmapi to install rmapi"))
    sub.add_parser("pair", help="Pair rmapi with reMarkable (prompts for one-time code)")
    _setup_ls_parser(sub.add_parser("ls", help="List files on reMarkable"))
    _setup_rm_parser(sub.add_parser("rm", help="Delete a file on reMarkable"))

    return parser


# --- command handlers -----------------------------------------------------


def cmd_publish(args) -> int:
    path = Path(args.path)
    rm_folder = args.rm_folder or cfg.get("remarkable.folder")
    if args.folder or path.is_dir():
        publisher.publish_folder(path, rm_folder, dry_run=args.dry_run)
    elif path.is_file():
        publisher.publish_page(path, rm_folder, dry_run=args.dry_run)
    else:
        _eprint(f"Error: {path} is not a file or folder")
        return 2
    return 0


def cmd_pull(args) -> int:
    if args.pull_all:
        rm_folder = args.rm_folder or cfg.get("remarkable.folder")
        vault = cfg.get("vault.path")
        listing = rmapi_client.ls(rm_folder)
        _eprint(listing)
        # rmapi ls format: "[f]\t<name>" for files, "[d]\t<name>" for dirs.
        # Parse the file marker separately and preserve the full name including
        # spaces (Copilot #4).
        names = []
        for ln in listing.splitlines():
            ln = ln.strip()
            if not ln or not ln.startswith("[f]"):
                continue
            # Strip the "[f]\t" marker; the rest is the full file name.
            name = ln[3:].lstrip("\t ").strip()
            if name:
                names.append(name)
        for name in names:
            md = Path(os.path.expanduser(vault)) / f"{name}.md"
            if md.is_file():
                retriever.retrieve(name, md, rm_folder=rm_folder)
            else:
                _eprint(f"  skipping {name}: no source .md at {md}")
        return 0

    if not args.page_name:
        _eprint("Error: pull requires a <page-name> (or --all)")
        return 2
    md_path = args.md_path
    if md_path is None:
        vault = cfg.get("vault.path")
        md_path = str(Path(os.path.expanduser(vault)) / f"{args.page_name}.md")
    retriever.retrieve(args.page_name, md_path, rm_folder=args.rm_folder)
    return 0


def cmd_config(args) -> int:
    if args.config_cmd == "set":
        cfg.set(args.key, args.value)
        # Mask secret values in confirmation output (Copilot #1).
        display = cfg._mask(str(args.value)) if "api_key" in resolve_key(args.key) else args.value
        _eprint(f"Set {args.key} = {display}")
    elif args.config_cmd == "show":
        print(cfg.show())
    elif args.config_cmd == "init":
        path = cfg.init_config()
        _eprint(f"Wrote default config to {path}")
    return 0


def _rmapi_asset_url() -> tuple[str, str]:
    """Return ``(download_url, extracted_binary_name)`` for this platform."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux":
        arch = "arm64" if machine in ("aarch64", "arm64") else "amd64"
        return (
            f"https://github.com/ddvk/rmapi/releases/latest/download/rmapi-linux-{arch}.tar.gz",
            "rmapi",
        )
    if system == "darwin":
        # ddvk/rmapi publishes macOS assets as ZIP, not tar.gz (Copilot #5).
        # Asset names: rmapi-macos-arm64.zip, rmapi-macos-intel.zip
        arch = "arm64" if machine == "arm64" else "intel"
        return (
            f"https://github.com/ddvk/rmapi/releases/latest/download/rmapi-macos-{arch}.zip",
            "rmapi",
        )
    if system in ("windows", "win32"):
        # ddvk/rmapi publishes Windows asset as rmapi-win64.zip (Copilot #5).
        return (
            "https://github.com/ddvk/rmapi/releases/latest/download/rmapi-win64.zip",
            "rmapi.exe",
        )
    raise RuntimeError(f"unsupported platform: {system} {machine}")


def cmd_setup(args) -> int:
    if args.rmapi:
        url, bin_name = _rmapi_asset_url()
        dest = Path.home() / ".local" / "bin"
        dest.mkdir(parents=True, exist_ok=True)
        _eprint(f"Downloading rmapi from {url} ...")
        import requests

        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / Path(url).name
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
            archive.write_bytes(resp.content)
            if archive.suffix == ".zip":
                with zipfile.ZipFile(archive) as z:
                    z.extractall(tmp)
            else:
                with tarfile.open(archive) as t:
                    t.extractall(tmp)
            src = Path(tmp) / bin_name
            shutil.copy2(src, dest / bin_name)
            os.chmod(dest / bin_name, 0o755)
        _eprint(f"Installed rmapi to {dest / bin_name}")
        _eprint("Ensure that directory is on your PATH.")
        return 0
    _eprint("Installing Playwright Chromium browser...")
    return subprocess.call([sys.executable, "-m", "playwright", "install", "chromium"])


def cmd_pair(args) -> int:
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