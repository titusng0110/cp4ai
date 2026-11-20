"""Install and remove the Finder Quick Action."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .resource_paths import resource_dir

WORKFLOW_NAME = "Copy 4 AI.workflow"
OLD_WORKFLOW_NAME = "Copy for AI.workflow"
SERVICES_DIR = Path.home() / "Library" / "Services"


def template_path() -> Path:
    return resource_dir() / "quickaction" / WORKFLOW_NAME


def installed_path() -> Path:
    return SERVICES_DIR / WORKFLOW_NAME


def _write_tree(source: Path, destination: Path) -> None:
    """Copy a workflow without preserving quarantine extended attributes."""
    if destination.exists():
        shutil.rmtree(destination)
    for root, _dirs, files in os.walk(source):
        relative = Path(root).relative_to(source)
        target_dir = destination / relative
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in files:
            (target_dir / name).write_bytes((Path(root) / name).read_bytes())


def _refresh_services() -> None:
    pbs = Path("/System/Library/CoreServices/pbs")
    if pbs.exists():
        subprocess.run(
            [str(pbs), "-flush"],
            check=False,
            capture_output=True,
            text=True,
        )


def install() -> Path:
    source = template_path()
    if not source.is_dir():
        raise FileNotFoundError(f"Quick Action template not found: {source}")
    destination = installed_path()
    SERVICES_DIR.mkdir(parents=True, exist_ok=True)
    old = SERVICES_DIR / OLD_WORKFLOW_NAME
    if old.exists():
        shutil.rmtree(old)
    _write_tree(source, destination)
    _refresh_services()
    return destination


def uninstall() -> None:
    for name in (WORKFLOW_NAME, OLD_WORKFLOW_NAME):
        destination = SERVICES_DIR / name
        if destination.exists():
            shutil.rmtree(destination)
    _refresh_services()


def is_installed() -> bool:
    return installed_path().is_dir()


LEGACY_WRAPPERS = {
    "cp4ai": "--cli-cp4ai",
    "md4ai": "--cli-md4ai",
}


def remove_legacy_cli_wrappers() -> list[Path]:
    """Remove wrappers written by older app builds.

    Those builds exposed app-backed CLI commands in ``~/.local/bin``.  They
    would shadow a uv-installed CLI, so a pure-GUI app removes only the
    wrappers it can identify.  uv symlinks are left alone.
    """
    removed: list[Path] = []
    bin_dir = Path.home() / ".local" / "bin"
    for name, marker in LEGACY_WRAPPERS.items():
        path = bin_dir / name
        try:
            if path.is_symlink() or not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if marker in text:
            try:
                path.unlink()
            except OSError:
                continue
            removed.append(path)
    return removed
